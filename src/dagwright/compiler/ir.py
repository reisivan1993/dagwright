"""Engine-neutral canonical pipeline intermediate representation."""

from collections.abc import Mapping, Sequence
from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StringConstraints
from pydantic.alias_generators import to_camel

StableId = Annotated[
    str,
    StringConstraints(pattern=r"^urn:dagwright:[a-z][a-z0-9_-]*(?::[a-z][a-z0-9_-]*){1,2}$"),
]


def _default_failure_policy() -> dict[str, JsonValue]:
    return {"action": "fail"}


def _default_retry_policy() -> dict[str, JsonValue]:
    return {"maxAttempts": 1}


class IRModel(BaseModel):
    """Strict and immutable canonical IR base model."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        frozen=True,
        strict=True,
        validate_by_alias=True,
        validate_by_name=True,
    )


class PipelineNode(IRModel):
    stable_id: StableId
    kind: Literal["source", "asset", "transformation", "quality", "anomaly"]
    name: str
    inputs: tuple[StableId, ...] = ()
    outputs: tuple[StableId, ...] = ()
    execution_semantics: dict[str, JsonValue] = Field(default_factory=dict)
    failure_policy: dict[str, JsonValue] = Field(default_factory=_default_failure_policy)
    retry_policy: dict[str, JsonValue] = Field(default_factory=_default_retry_policy)
    resource_hints: dict[str, JsonValue] | None = None
    security_context: dict[str, JsonValue] = Field(default_factory=dict)
    lineage_metadata: dict[str, JsonValue] = Field(default_factory=dict)
    schema_in: dict[str, JsonValue] | None = None
    schema_out: dict[str, JsonValue] | None = None
    source_contract_location: str
    extension_fields: dict[str, JsonValue] = Field(default_factory=dict)


class DependencyEdge(IRModel):
    stable_id: StableId
    source: StableId
    target: StableId
    kind: Literal["reads", "depends_on", "transforms", "validates", "observes"]


class IRExecution(IRModel):
    transform_engine: str
    orchestrator: str
    target_catalog: str
    schedule: str | None
    resources: dict[str, JsonValue] | None


class IRGovernance(IRModel):
    data_classification: str
    production_repair_policy: str
    pii_fields: tuple[str, ...]
    retention: str | None


class PipelineIR(IRModel):
    ir_version: Literal["dagwright.ir/v1alpha1"]
    data_product_id: StableId
    contract_api_version: str
    contract_version: str
    contract_digest: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
    nodes: tuple[PipelineNode, ...]
    edges: tuple[DependencyEdge, ...]
    operational_contracts: dict[str, JsonValue]
    execution: IRExecution
    governance: IRGovernance


class SchemaCompatibilityHook(Protocol):
    """Extension point for schema checks without coupling the IR to an engine."""

    @property
    def name(self) -> str: ...

    def check(
        self,
        upstream: PipelineNode,
        downstream: PipelineNode,
    ) -> Sequence[str]: ...


def node_index(nodes: Sequence[PipelineNode]) -> Mapping[str, PipelineNode]:
    """Index nodes by stable ID for compatibility hooks and graph consumers."""
    return {node.stable_id: node for node in nodes}
