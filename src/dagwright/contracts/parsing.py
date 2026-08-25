"""JSON and YAML parsing for DataProduct contracts."""

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal, cast

import yaml
from pydantic import ValidationError

from dagwright.contracts.models import DataProduct

ContractFormat = Literal["json", "yaml"]


class ContractParseError(ValueError):
    """A syntax, shape, or model-validation error with source context."""

    def __init__(
        self,
        message: str,
        *,
        source: str = "<string>",
        line: int | None = None,
        column: int | None = None,
    ) -> None:
        self.source = source
        self.line = line
        self.column = column
        position = source
        if line is not None:
            position += f":{line}"
            if column is not None:
                position += f":{column}"
        super().__init__(f"{position}: {message}")


class _UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that refuses ambiguous duplicate mappings."""


def _construct_unique_mapping(
    loader: _UniqueKeyLoader,
    node: yaml.MappingNode,
    deep: bool = False,
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str):
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "contract object keys must be strings",
                key_node.start_mark,
            )
        if key in result:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"duplicate key {key!r}",
                key_node.start_mark,
            )
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key {key!r}")
        result[key] = value
    return result


def parse_contract(
    text: str,
    *,
    format: ContractFormat,
    source: str = "<string>",
) -> DataProduct:
    """Parse and strictly validate one JSON or YAML DataProduct contract."""
    try:
        if format == "json":
            raw = json.loads(text, object_pairs_hook=_unique_json_object)
        else:
            raw = yaml.load(text, Loader=_UniqueKeyLoader)
    except json.JSONDecodeError as error:
        raise ContractParseError(
            error.msg,
            source=source,
            line=error.lineno,
            column=error.colno,
        ) from error
    except yaml.MarkedYAMLError as error:
        mark = error.problem_mark
        raise ContractParseError(
            error.problem or str(error),
            source=source,
            line=mark.line + 1 if mark else None,
            column=mark.column + 1 if mark else None,
        ) from error
    except ValueError as error:
        raise ContractParseError(str(error), source=source) from error

    if not isinstance(raw, Mapping):
        raise ContractParseError("contract root must be an object", source=source)
    try:
        return DataProduct.model_validate(cast(dict[str, Any], raw))
    except ValidationError as error:
        details = "; ".join(
            f"{_format_location(item['loc'])}: {item['msg']}" for item in error.errors()
        )
        raise ContractParseError(details, source=source) from error


def parse_contract_file(path: Path) -> DataProduct:
    """Parse a contract file, inferring its format from the extension."""
    suffix = path.suffix.lower()
    formats: dict[str, ContractFormat] = {".json": "json", ".yaml": "yaml", ".yml": "yaml"}
    if suffix not in formats:
        raise ContractParseError(
            "unsupported contract format; expected .json, .yaml, or .yml",
            source=str(path),
        )
    try:
        text = path.read_text()
    except OSError as error:
        raise ContractParseError(str(error), source=str(path)) from error
    return parse_contract(text, format=formats[suffix], source=str(path))


def _format_location(location: tuple[int | str, ...]) -> str:
    result = "$"
    for part in location:
        result += f"[{part}]" if isinstance(part, int) else f".{part}"
    return result
