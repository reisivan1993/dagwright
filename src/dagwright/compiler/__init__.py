"""Deterministic contract normalization and canonical IR compilation."""

from dagwright.compiler.canonical import canonical_bytes, canonical_digest, normalize_contract
from dagwright.compiler.compile import CompilationResult, compile_contract
from dagwright.compiler.errors import (
    CycleError,
    MissingReferenceError,
    ReferenceResolutionError,
    SchemaCompatibilityError,
    SQLValidationError,
)
from dagwright.compiler.ir import (
    DependencyEdge,
    PipelineIR,
    PipelineNode,
    SchemaCompatibilityHook,
)
from dagwright.compiler.planning import ExecutionPlan, PlanStep, build_execution_plan
from dagwright.compiler.sql import load_validated_sql

__all__ = [
    "CompilationResult",
    "CycleError",
    "DependencyEdge",
    "ExecutionPlan",
    "MissingReferenceError",
    "PipelineIR",
    "PipelineNode",
    "PlanStep",
    "ReferenceResolutionError",
    "SQLValidationError",
    "SchemaCompatibilityError",
    "SchemaCompatibilityHook",
    "build_execution_plan",
    "canonical_bytes",
    "canonical_digest",
    "compile_contract",
    "load_validated_sql",
    "normalize_contract",
]
