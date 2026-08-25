"""Deterministic environment overlays for DataProduct contracts."""

import copy
import json
from collections.abc import MutableMapping, MutableSequence
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError, model_validator
from pydantic.alias_generators import to_camel

from dagwright.contracts.models import DataProduct, Name


class OverlayError(ValueError):
    """An overlay syntax, conflict, or application failure."""


class OverlayModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        frozen=True,
        strict=True,
        validate_by_alias=True,
        validate_by_name=True,
    )


class OverlayPatch(OverlayModel):
    path: str = Field(pattern=r"^/(?:[^/~]|~[01])+(?:/(?:[^/~]|~[01])+)*$")
    value: JsonValue


class DataProductOverlay(OverlayModel):
    api_version: Literal["dagwright.io/v1alpha1"]
    kind: Literal["DataProductOverlay"]
    name: Name
    patches: list[OverlayPatch] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_nonoverlapping_paths(self) -> "DataProductOverlay":
        _reject_overlaps([(self.name, patch.path) for patch in self.patches])
        immutable = (("apiVersion",), ("kind",), ("version",), ("metadata", "name"))
        for patch in self.patches:
            tokens = _tokens(patch.path)
            for protected in immutable:
                shared = min(len(tokens), len(protected))
                if tokens[:shared] == protected[:shared]:
                    raise OverlayError(f"overlay may not replace contract identity: {patch.path}")
        return self


def parse_overlay_file(path: Path) -> DataProductOverlay:
    """Parse one strict JSON or YAML overlay document."""
    suffix = path.suffix.lower()
    if suffix not in {".json", ".yaml", ".yml"}:
        raise OverlayError(f"{path}: unsupported overlay format; expected JSON or YAML")
    try:
        text = path.read_text()
        raw: Any = json.loads(text) if suffix == ".json" else yaml.safe_load(text)
        return DataProductOverlay.model_validate(raw, strict=True)
    except (OSError, ValueError, yaml.YAMLError, ValidationError) as error:
        raise OverlayError(f"invalid overlay {path}: {error}") from error


def apply_overlays(contract: DataProduct, overlays: list[DataProductOverlay]) -> DataProduct:
    """Apply disjoint replacement patches in a CLI-order-independent sequence."""
    names = [overlay.name for overlay in overlays]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise OverlayError(f"duplicate overlay names: {', '.join(duplicates)}")
    locations = [(overlay.name, patch.path) for overlay in overlays for patch in overlay.patches]
    _reject_overlaps(locations)
    document = copy.deepcopy(contract.model_dump(mode="json", by_alias=True))
    ordered = sorted(
        ((overlay.name, patch) for overlay in overlays for patch in overlay.patches),
        key=lambda item: (item[0], item[1].path),
    )
    for overlay_name, patch in ordered:
        _replace(document, patch.path, patch.value, overlay_name)
    try:
        return DataProduct.model_validate(document)
    except ValidationError as error:
        raise OverlayError(f"overlays produce an invalid DataProduct: {error}") from error


def _reject_overlaps(locations: list[tuple[str, str]]) -> None:
    ordered = sorted(locations, key=lambda item: item[1])
    for index, (owner, path) in enumerate(ordered):
        tokens = _tokens(path)
        for other_owner, other_path in ordered[index + 1 :]:
            other_tokens = _tokens(other_path)
            shared = min(len(tokens), len(other_tokens))
            if tokens[:shared] == other_tokens[:shared]:
                raise OverlayError(
                    f"overlapping overlay patches {owner}:{path} and {other_owner}:{other_path}"
                )


def _tokens(pointer: str) -> tuple[str, ...]:
    return tuple(token.replace("~1", "/").replace("~0", "~") for token in pointer[1:].split("/"))


def _replace(document: dict[str, Any], pointer: str, value: JsonValue, owner: str) -> None:
    tokens = _tokens(pointer)
    parent: MutableMapping[str, Any] | MutableSequence[Any] = document
    for token in tokens[:-1]:
        if isinstance(parent, MutableSequence):
            index = _index(token, len(parent), pointer, owner)
            child = parent[index]
        else:
            if token not in parent:
                raise OverlayError(f"overlay {owner!r} path does not exist: {pointer}")
            child = parent[token]
        if not isinstance(child, (MutableMapping, MutableSequence)):
            raise OverlayError(f"overlay {owner!r} path traverses a scalar: {pointer}")
        parent = child
    final = tokens[-1]
    if isinstance(parent, MutableSequence):
        parent[_index(final, len(parent), pointer, owner)] = value
    else:
        if final not in parent:
            raise OverlayError(f"overlay {owner!r} path does not exist: {pointer}")
        parent[final] = value


def _index(token: str, length: int, pointer: str, owner: str) -> int:
    if not token.isdigit() or int(token) >= length:
        raise OverlayError(f"overlay {owner!r} has invalid list index in path: {pointer}")
    return int(token)
