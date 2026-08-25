"""Safe, generation-only adapter contracts."""

import hashlib
from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, JsonValue
from pydantic.alias_generators import to_camel

from dagwright.compiler.ir import PipelineIR


class AdapterModel(BaseModel):
    """Strict machine-readable adapter metadata base."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        frozen=True,
        strict=True,
        validate_by_alias=True,
        validate_by_name=True,
    )


class AdapterCapabilities(AdapterModel):
    api_version: Literal["dagwright.io/adapter-capabilities/v1alpha1"]
    name: str
    adapter_version: str
    target: str
    target_version: str
    contract_versions: tuple[str, ...]
    ir_versions: tuple[str, ...]
    generation_only: bool
    batch: bool
    streaming: bool
    cdc: Literal["unsupported", "delegated_to_source"]
    checkpointing: bool
    watermarks: Literal["unsupported", "delegated_to_workload"]
    exactly_once_scope: Literal["none", "task", "pipeline"]
    schema_evolution: bool
    rollback: bool
    dry_run: bool
    lineage: bool
    cost_visibility: bool
    schedules: tuple[str, ...]
    quality_gates: Literal["structural_fail_closed"]
    operational_contracts: Literal["quality_fail_closed_others_delegated"]


class CapabilityViolation(AdapterModel):
    code: str
    path: str
    message: str


class UnsupportedSemanticsError(ValueError):
    """All deterministic capability violations for one generation request."""

    def __init__(self, adapter: str, violations: tuple[CapabilityViolation, ...]) -> None:
        self.adapter = adapter
        self.violations = violations
        details = "; ".join(
            f"{violation.path} [{violation.code}]: {violation.message}" for violation in violations
        )
        super().__init__(f"adapter {adapter!r} cannot generate requested semantics: {details}")


class ArtifactMetadata(AdapterModel):
    path: str
    media_type: str
    role: Literal["orchestrator_dag"]
    sha256: str
    size: int = Field(ge=0)


class LineageMetadata(AdapterModel):
    edge_id: str
    edge_kind: str
    upstream_stable_id: str
    downstream_stable_id: str
    upstream_task_id: str
    downstream_task_id: str


class TaskMetadata(AdapterModel):
    stable_id: str
    task_id: str
    kind: str
    source_contract_location: str
    retries: int = Field(ge=0)
    quality_gate: bool
    severity: str | None


class ArtifactManifest(AdapterModel):
    api_version: Literal["dagwright.io/artifact-manifest/v1alpha1"]
    adapter: str
    adapter_version: str
    target_version: str
    generation_mode: Literal["fail_closed_scaffold"]
    input_ir_digest: str
    contract_digest: str
    delegated_operational_contracts: dict[str, JsonValue]
    artifacts: tuple[ArtifactMetadata, ...]
    tasks: tuple[TaskMetadata, ...]
    lineage: tuple[LineageMetadata, ...]


@dataclass(frozen=True)
class GeneratedArtifact:
    path: str
    media_type: str
    content: bytes

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()


@dataclass(frozen=True)
class ArtifactBundle:
    artifact: GeneratedArtifact
    manifest: ArtifactManifest
    manifest_bytes: bytes


class GeneratorAdapter(Protocol):
    """An adapter that validates and generates files but cannot execute or deploy."""

    def capabilities(self) -> AdapterCapabilities: ...

    def validate(self, ir: PipelineIR) -> tuple[CapabilityViolation, ...]: ...

    def generate(self, ir: PipelineIR) -> ArtifactBundle: ...
