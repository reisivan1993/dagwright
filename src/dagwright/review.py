"""Build and write deterministic, reviewable compilation bundles."""

import hashlib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from dagwright import __version__
from dagwright.adapters.airflow import Airflow3Adapter, capability_bytes
from dagwright.adapters.spark import SparkIcebergAdapter
from dagwright.compiler import CompilationResult
from dagwright.compiler.canonical import canonical_bytes
from dagwright.compiler.planning import build_execution_plan
from dagwright.validation import validate_bundle_files

CompilationTarget = Literal["airflow", "spark", "all"]


class ReviewModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        frozen=True,
        strict=True,
        validate_by_alias=True,
        validate_by_name=True,
    )


class ReviewFileMetadata(ReviewModel):
    path: str
    role: Literal[
        "normalized_contract",
        "pipeline_ir",
        "adapter_capabilities",
        "adapter_manifest",
        "orchestrator_dag",
        "execution_plan",
        "spark_job",
        "iceberg_metadata",
        "workload_manifest",
    ]
    media_type: str
    sha256: str
    size: int = Field(ge=0)


class CompilationManifest(ReviewModel):
    api_version: Literal["dagwright.io/compilation-manifest/v1alpha1"]
    compiler: Literal["dagwright"]
    compiler_version: str
    data_product_id: str
    contract_version: str
    contract_digest: str
    ir_version: str
    ir_digest: str
    adapter: str
    adapter_version: str
    generation_only: bool
    files: tuple[ReviewFileMetadata, ...]


@dataclass(frozen=True)
class ReviewFile:
    path: str
    role: Literal[
        "normalized_contract",
        "pipeline_ir",
        "adapter_capabilities",
        "adapter_manifest",
        "orchestrator_dag",
        "execution_plan",
        "spark_job",
        "iceberg_metadata",
        "workload_manifest",
    ]
    media_type: str
    content: bytes

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()


@dataclass(frozen=True)
class ReviewBundle:
    files: tuple[ReviewFile, ...]
    manifest: CompilationManifest
    manifest_bytes: bytes

    @property
    def manifest_sha256(self) -> str:
        return hashlib.sha256(self.manifest_bytes).hexdigest()


class ReviewWriteError(ValueError):
    """Raised when a review bundle cannot be written safely."""


def build_review_bundle(
    compilation: CompilationResult,
    adapter: Airflow3Adapter | None = None,
    *,
    target: CompilationTarget = "all",
    sql_by_transformation: dict[str, str] | None = None,
) -> ReviewBundle:
    """Generate every deterministic file required to review one compilation."""
    selected = adapter or Airflow3Adapter()
    generated = selected.generate(compilation.ir) if target in {"airflow", "all"} else None
    spark = (
        SparkIcebergAdapter().generate(compilation.ir, sql_by_transformation or {})
        if target in {"spark", "all"}
        else None
    )
    target_files: list[ReviewFile] = []
    if generated is not None:
        target_files.extend(
            [
                ReviewFile(
                    path="adapters/airflow/capabilities.json",
                    role="adapter_capabilities",
                    media_type="application/json",
                    content=capability_bytes(),
                ),
                ReviewFile(
                    path="adapters/airflow/manifest.json",
                    role="adapter_manifest",
                    media_type="application/json",
                    content=generated.manifest_bytes,
                ),
                ReviewFile(
                    path=generated.artifact.path,
                    role="orchestrator_dag",
                    media_type=generated.artifact.media_type,
                    content=generated.artifact.content,
                ),
            ]
        )
    if spark is not None:
        target_files.extend(
            ReviewFile(
                path=item.path,
                role=item.role,  # type: ignore[arg-type]
                media_type=item.media_type,
                content=item.content,
            )
            for item in spark.artifacts
        )
        target_files.append(
            ReviewFile(
                path="adapters/spark/manifest.json",
                role="workload_manifest",
                media_type="application/json",
                content=spark.manifest_bytes,
            )
        )
    plan_bytes = canonical_bytes(build_execution_plan(compilation.ir))
    files = tuple(
        sorted(
            (
                ReviewFile(
                    path="contract.normalized.json",
                    role="normalized_contract",
                    media_type="application/json",
                    content=compilation.contract_bytes,
                ),
                ReviewFile(
                    path="pipeline.ir.json",
                    role="pipeline_ir",
                    media_type="application/json",
                    content=compilation.ir_bytes,
                ),
                ReviewFile(
                    path="plan.json",
                    role="execution_plan",
                    media_type="application/json",
                    content=plan_bytes,
                ),
                *target_files,
            ),
            key=lambda item: item.path,
        )
    )
    capabilities = selected.capabilities()
    manifest = CompilationManifest(
        api_version="dagwright.io/compilation-manifest/v1alpha1",
        compiler="dagwright",
        compiler_version=__version__,
        data_product_id=compilation.ir.data_product_id,
        contract_version=compilation.ir.contract_version,
        contract_digest=compilation.contract_digest,
        ir_version=compilation.ir.ir_version,
        ir_digest=compilation.ir_digest,
        adapter={
            "airflow": capabilities.name,
            "spark": "spark-iceberg",
            "all": "airflow3+spark-iceberg",
        }[target],
        adapter_version=capabilities.adapter_version,
        generation_only=True,
        files=tuple(
            ReviewFileMetadata(
                path=item.path,
                role=item.role,
                media_type=item.media_type,
                sha256=item.sha256,
                size=len(item.content),
            )
            for item in files
        ),
    )
    bundle = ReviewBundle(files=files, manifest=manifest, manifest_bytes=canonical_bytes(manifest))
    validate_bundle_files({item.path: item.content for item in bundle.files})
    return bundle


def write_review_bundle(bundle: ReviewBundle, output: Path) -> None:
    """Write a bundle to a new or empty directory without executing its contents."""
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ReviewWriteError(f"output directory must be absent or empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    for item in bundle.files:
        relative = _safe_relative_path(item.path)
        destination = output.joinpath(*relative.parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(item.content)
    (output / "manifest.json").write_bytes(bundle.manifest_bytes)


def _safe_relative_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise ReviewWriteError(f"unsafe generated artifact path: {value!r}")
    return path
