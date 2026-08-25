"""Strict contracts for deterministic local execution verification."""

from pathlib import PurePosixPath
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from pydantic.alias_generators import to_camel

Name = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*$")]
RelativePath = Annotated[str, StringConstraints(min_length=1)]


class VerificationModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        frozen=True,
        strict=True,
        validate_by_alias=True,
        validate_by_name=True,
    )


class Fixture(VerificationModel):
    view: Name
    path: RelativePath

    @model_validator(mode="after")
    def safe_path(self) -> Self:
        _require_safe_relative_path(self.path)
        return self


class NegativeControl(VerificationModel):
    name: Name
    fixtures: list[Fixture] = Field(min_length=1)


class ExpectedOutput(VerificationModel):
    rows: RelativePath
    schema_path: RelativePath = Field(alias="schema", serialization_alias="schema")
    order_by: list[Name] = Field(min_length=1)

    @model_validator(mode="after")
    def safe_paths(self) -> Self:
        _require_safe_relative_path(self.rows)
        _require_safe_relative_path(self.schema_path)
        return self


class VerificationSuite(VerificationModel):
    api_version: Literal["dagwright.io/verification-suite/v1alpha1"]
    kind: Literal["VerificationSuite"]
    name: Name
    transformation: Name
    fixtures: list[Fixture] = Field(min_length=1)
    expected: ExpectedOutput
    negative_controls: list[NegativeControl] = Field(min_length=1)
    attempts: int = Field(default=2, ge=2, le=10)

    @model_validator(mode="after")
    def unique_names(self) -> Self:
        _require_unique("fixture views", [item.view for item in self.fixtures])
        _require_unique("negative controls", [item.name for item in self.negative_controls])
        for control in self.negative_controls:
            _require_unique(
                f"fixture views in negative control {control.name!r}",
                [item.view for item in control.fixtures],
            )
        return self


def _require_safe_relative_path(value: str) -> None:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError(f"path must be a safe relative path: {value!r}")


def _require_unique(label: str, values: list[str]) -> None:
    duplicates = sorted({value for value in values if values.count(value) > 1})
    if duplicates:
        raise ValueError(f"duplicate {label}: {', '.join(duplicates)}")
