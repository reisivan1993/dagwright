"""Strict domain models for the ``dagwright.io/v1alpha1`` DataProduct contract."""

from collections.abc import Mapping
from typing import Annotated, Any, ClassVar, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    GetJsonSchemaHandler,
    JsonValue,
    StringConstraints,
    model_validator,
)
from pydantic.alias_generators import to_camel
from pydantic.json_schema import JsonSchemaValue

API_VERSION = "dagwright.io/v1alpha1"
EXTENSION_PATTERN = r"^x-[a-z][a-z0-9]*(?:[./-][a-z][a-z0-9]*)*$"
NAME_PATTERN = r"^[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*$"
SEMANTIC_VERSION_PATTERN = (
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
ISO_DURATION_PATTERN = (
    r"^P(?:"
    r"[0-9]+D(?:T(?:[0-9]+H)?(?:[0-9]+M)?(?:[0-9]+(?:\.[0-9]+)?S)?)?"
    r"|T(?:[0-9]+H(?:[0-9]+M)?(?:[0-9]+(?:\.[0-9]+)?S)?"
    r"|[0-9]+M(?:[0-9]+(?:\.[0-9]+)?S)?"
    r"|[0-9]+(?:\.[0-9]+)?S)"
    r")$"
)

Name = Annotated[str, StringConstraints(pattern=NAME_PATTERN, min_length=1, max_length=128)]
SemanticVersion = Annotated[str, StringConstraints(pattern=SEMANTIC_VERSION_PATTERN)]
Duration = Annotated[str, StringConstraints(pattern=ISO_DURATION_PATTERN)]
NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ContractModel(BaseModel):
    """Strict contract base with explicitly namespaced extension properties."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="allow",
        frozen=True,
        strict=True,
        validate_by_alias=True,
        validate_by_name=False,
    )

    __pydantic_extra__: dict[str, JsonValue] = Field(init=False)
    extension_pattern: ClassVar[str] = EXTENSION_PATTERN

    @model_validator(mode="before")
    @classmethod
    def reject_unowned_fields(cls, value: Any) -> Any:
        """Reject extras unless their key identifies an extension namespace."""
        if not isinstance(value, Mapping):
            return value
        aliases = {field.alias for field in cls.model_fields.values()}
        unknown = sorted(
            key
            for key in value
            if isinstance(key, str) and key not in aliases and not _is_extension_key(key)
        )
        if unknown:
            fields = ", ".join(repr(field) for field in unknown)
            raise ValueError(
                f"unknown field(s): {fields}; custom fields must use a namespaced 'x-' key"
            )
        return value

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: Any,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        """Express the runtime extension-key policy in published JSON Schema."""
        schema = handler(core_schema)
        schema["additionalProperties"] = False
        schema["patternProperties"] = {
            EXTENSION_PATTERN: {
                "description": "Namespaced extension value.",
            }
        }
        return schema


def _is_extension_key(key: str) -> bool:
    import re

    return re.fullmatch(EXTENSION_PATTERN, key) is not None


class Metadata(ContractModel):
    """Ownership and identity metadata."""

    name: Name
    owner: NonEmptyString
    environment: Name
    description: str | None = None
    labels: dict[Name, NonEmptyString] = Field(default_factory=dict)


class Capture(ContractModel):
    """How a source is read and how source deletes are represented."""

    mode: Literal["batch", "cdc", "stream"]
    delete_semantics: Literal["ignore", "hard_delete", "soft_delete", "tombstone"] = "ignore"
    cursor_field: Name | None = None

    @model_validator(mode="after")
    def require_cursor_for_incremental_batch(self) -> Self:
        if self.mode == "batch" and self.cursor_field is not None:
            return self
        if self.mode != "batch" and self.cursor_field is not None:
            raise ValueError("cursorField is only valid when capture.mode is 'batch'")
        return self


class Source(ContractModel):
    """A named external data source."""

    name: Name
    type: Name
    connection_ref: Annotated[str, StringConstraints(pattern=r"^secret://[^\s]+$")]
    object: NonEmptyString | None = None
    capture: Capture


class Transformation(ContractModel):
    """A reviewable transformation implementation reference."""

    id: Name
    type: Literal["sql", "python"]
    inputs: list[Name] = Field(min_length=1)
    output: Name
    sql_ref: NonEmptyString | None = None
    python_ref: NonEmptyString | None = None

    @model_validator(mode="after")
    def require_matching_implementation(self) -> Self:
        expected = self.sql_ref if self.type == "sql" else self.python_ref
        unexpected = self.python_ref if self.type == "sql" else self.sql_ref
        if expected is None:
            raise ValueError(f"{self.type} transformation requires {self.type}Ref")
        if unexpected is not None:
            raise ValueError("transformation may reference only its declared implementation type")
        return self


class Asset(ContractModel):
    """A materialized or logical data asset."""

    name: Name
    type: Name
    mode: Literal["append", "append_changes", "current_state", "snapshot"]
    source: NonEmptyString | None = None
    inputs: list[Name] = Field(default_factory=list)
    primary_key: list[Name] = Field(default_factory=list)
    retention: Duration | None = None
    transformation_ids: list[Name] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_one_origin(self) -> Self:
        if (self.source is None) == (not self.inputs):
            raise ValueError("asset requires exactly one origin: source or non-empty inputs")
        if self.mode == "current_state" and not self.primary_key:
            raise ValueError("current_state asset requires a non-empty primaryKey")
        return self


class QualityRule(ContractModel):
    """A deterministic data-quality expectation."""

    id: Name
    type: Literal[
        "not_null",
        "unique",
        "referential_integrity",
        "accepted_values",
        "expression",
    ]
    asset: Name
    fields: list[Name] = Field(min_length=1)
    reference: NonEmptyString | None = None
    values: list[str | int | float | bool] | None = None
    expression: NonEmptyString | None = None
    severity: Literal["warning", "error"] = "error"

    @model_validator(mode="after")
    def validate_parameters(self) -> Self:
        if self.type == "referential_integrity" and self.reference is None:
            raise ValueError("referential_integrity quality rule requires reference")
        if self.type != "referential_integrity" and self.reference is not None:
            raise ValueError("reference is only valid for referential_integrity quality rules")
        if self.type == "accepted_values" and not self.values:
            raise ValueError("accepted_values quality rule requires non-empty values")
        if self.type != "accepted_values" and self.values is not None:
            raise ValueError("values is only valid for accepted_values quality rules")
        if self.type == "expression" and self.expression is None:
            raise ValueError("expression quality rule requires expression")
        if self.type != "expression" and self.expression is not None:
            raise ValueError("expression is only valid for expression quality rules")
        if self.type in {"accepted_values", "referential_integrity"} and len(self.fields) != 1:
            raise ValueError(f"{self.type} quality rule requires exactly one field")
        return self


class AnomalyRule(ContractModel):
    """A declared statistical anomaly signal; evaluation is outside this checkpoint."""

    id: Name
    asset: Name
    metric: Literal["row_count", "freshness", "null_rate", "latency", "cost"]
    method: Literal["static_threshold", "relative_change", "standard_deviation"]
    threshold: Annotated[float, Field(gt=0)]
    window: Duration
    severity: Literal["warning", "error"] = "warning"


class FreshnessContract(ContractModel):
    target: Duration
    critical_after: Duration


class RowRange(ContractModel):
    min: Annotated[int, Field(ge=0)]
    max: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def ordered_range(self) -> Self:
        if self.min > self.max:
            raise ValueError("expectedRowsPerHour.min must be less than or equal to max")
        return self


class VolumeContract(ContractModel):
    expected_rows_per_hour: RowRange


class LateData(ContractModel):
    watermark: Duration
    action: Literal["drop", "quarantine", "recompute_window"]


class DeliveryContract(ContractModel):
    duplicates: Literal["forbidden", "possible"]
    ordering: Literal["none", "per_partition", "total"]
    late_data: LateData | None = None


class ContractExpectations(ContractModel):
    freshness: FreshnessContract | None = None
    quality: list[QualityRule] = Field(default_factory=list)
    anomalies: list[AnomalyRule] = Field(default_factory=list)
    volume: VolumeContract | None = None
    delivery: DeliveryContract


class ResourceHints(ContractModel):
    cpu: Annotated[float, Field(gt=0)] | None = None
    memory: Annotated[str, StringConstraints(pattern=r"^[1-9][0-9]*(?:Mi|Gi)$")] | None = None


class RetryPolicy(ContractModel):
    """Portable task-attempt definition; adapters map attempts to engine retries."""

    max_attempts: Annotated[int, Field(ge=1, le=100)] = 1


class IdempotencyPolicy(ContractModel):
    """Declared write behavior used by workload generators and reviewers."""

    mode: Literal["replace_output", "merge_by_key", "append_once"] = "replace_output"
    key_fields: list[Name] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_keys_for_merge(self) -> Self:
        if self.mode == "merge_by_key" and not self.key_fields:
            raise ValueError("merge_by_key idempotency requires non-empty keyFields")
        if self.mode != "merge_by_key" and self.key_fields:
            raise ValueError("keyFields are only valid for merge_by_key idempotency")
        return self


class Execution(ContractModel):
    """Requested engine roles, not generated deployment configuration."""

    transform_engine: Name
    orchestrator: Name
    target_catalog: Name
    schedule: NonEmptyString | None = None
    resources: ResourceHints | None = None
    retry: RetryPolicy = Field(default_factory=RetryPolicy)
    idempotency: IdempotencyPolicy = Field(default_factory=IdempotencyPolicy)


class Governance(ContractModel):
    """Classification and production-change controls."""

    data_classification: Literal["public", "internal", "confidential", "restricted"]
    production_repair_policy: Literal["disabled", "approval_required", "bounded_autonomous"]
    pii_fields: list[NonEmptyString] = Field(default_factory=list)
    retention: Duration | None = None


class DataProduct(ContractModel):
    """The root ``dagwright.io/v1alpha1`` contract."""

    api_version: Literal["dagwright.io/v1alpha1"]
    kind: Literal["DataProduct"]
    version: SemanticVersion
    metadata: Metadata
    sources: list[Source] = Field(min_length=1)
    assets: list[Asset] = Field(min_length=1)
    transformations: list[Transformation] = Field(default_factory=list)
    contracts: ContractExpectations
    execution: Execution
    governance: Governance

    @model_validator(mode="after")
    def unique_identifiers(self) -> Self:
        _require_unique("source names", [source.name for source in self.sources])
        _require_unique("asset names", [asset.name for asset in self.assets])
        _require_unique(
            "transformation ids", [transformation.id for transformation in self.transformations]
        )
        _require_unique("quality rule ids", [rule.id for rule in self.contracts.quality])
        _require_unique("anomaly rule ids", [rule.id for rule in self.contracts.anomalies])
        return self


def _require_unique(label: str, values: list[str]) -> None:
    duplicates = sorted({value for value in values if values.count(value) > 1})
    if duplicates:
        raise ValueError(f"duplicate {label}: {', '.join(duplicates)}")
