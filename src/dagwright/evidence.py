"""Deterministic evidence models for local pipeline verification."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pydantic.alias_generators import to_camel


class EvidenceModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        frozen=True,
        strict=True,
        validate_by_alias=True,
        validate_by_name=True,
    )


class EvidenceInput(EvidenceModel):
    path: str
    sha256: str


class SchemaFieldEvidence(EvidenceModel):
    name: str
    type: str
    nullable: bool


class QualityEvidence(EvidenceModel):
    rule_id: str
    rule_type: str
    asset: str
    passed: bool
    failure_count: int = Field(ge=0)


class RunEvidence(EvidenceModel):
    attempt: int = Field(ge=1)
    row_count: int = Field(ge=0)
    output_digest: str


class ExecutionEvidence(EvidenceModel):
    api_version: Literal["dagwright.io/execution-evidence/v1alpha1"]
    data_product_id: str
    contract_digest: str
    ir_digest: str
    engine: Literal["apache-spark-3.5"]
    table_format: Literal["apache-iceberg"]
    table: str
    inputs: tuple[EvidenceInput, ...]
    output_schema: tuple[SchemaFieldEvidence, ...] = Field(
        alias="schema", serialization_alias="schema"
    )
    expected_output_digest: str
    runs: tuple[RunEvidence, ...]
    quality: tuple[QualityEvidence, ...]
    quality_negative_control: tuple[QualityEvidence, ...]
    quality_negative_control_passed: bool
    idempotency_mode: str
    idempotency_passed: bool
    verification_passed: bool


def read_execution_evidence(path: Path) -> ExecutionEvidence:
    """Load a strict execution-evidence document with a useful path-aware error."""
    try:
        return ExecutionEvidence.model_validate_json(path.read_bytes(), strict=True)
    except (OSError, ValidationError) as error:
        raise ValueError(f"invalid execution evidence {path}: {error}") from error
