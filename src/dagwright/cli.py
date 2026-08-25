"""Command-line interface for DAGwright."""

import shutil
import subprocess
from collections import Counter
from pathlib import Path
from typing import Annotated, Never, cast

import typer

from dagwright import __version__
from dagwright.adapters.airflow import Airflow3Adapter
from dagwright.adapters.base import UnsupportedSemanticsError
from dagwright.compiler import (
    CompilationResult,
    build_execution_plan,
    compile_contract,
    load_validated_sql,
)
from dagwright.compiler.errors import CompilerError
from dagwright.contracts import ContractParseError, parse_contract_file
from dagwright.diagnostics import run_checks
from dagwright.evidence import read_execution_evidence
from dagwright.review import (
    CompilationTarget,
    ReviewBundle,
    ReviewWriteError,
    build_review_bundle,
    write_review_bundle,
)
from dagwright.validation import StaticValidationError, inspect_manifest
from dagwright.verification import VerificationSuiteParseError, parse_verification_suite_file

app = typer.Typer(
    name="dagwright",
    help="DAGwright: an engine-neutral agentic compiler and control plane.",
    no_args_is_help=True,
)


@app.command()
def version() -> None:
    """Print the installed DAGwright version."""
    typer.echo(__version__)


@app.command()
def doctor() -> None:
    """Check whether the local development environment is usable."""
    checks = run_checks()
    for check in checks:
        status = "ok" if check.passed else "fail"
        typer.echo(f"[{status}] {check.name}: {check.detail}")
    if not all(check.passed for check in checks):
        raise typer.Exit(code=1)
    typer.echo("DAGwright is ready.")


@app.command("validate")
def validate_command(
    contract: Annotated[Path, typer.Argument(help="DataProduct JSON or YAML file")],
) -> None:
    """Validate a contract, references, graph, and target capabilities."""
    compilation, bundle = _prepare(contract)
    typer.echo(f"VALID {compilation.contract.metadata.name} ({compilation.contract.version})")
    typer.echo(f"  contract sha256: {compilation.contract_digest}")
    typer.echo(
        f"  canonical IR: {len(compilation.ir.nodes)} nodes, "
        f"{len(compilation.ir.edges)} edges, sha256:{compilation.ir_digest}"
    )
    typer.echo(f"  adapter: {bundle.manifest.adapter} (supported, generation-only)")


@app.command("compile")
def compile_command(
    contract: Annotated[Path, typer.Argument(help="DataProduct JSON or YAML file")],
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="New or empty review output directory"),
    ] = Path("build"),
    target: Annotated[
        str,
        typer.Option("--target", help="Artifact target: airflow, spark, or all"),
    ] = "all",
) -> None:
    """Compile a contract into deterministic, statically validated artifacts."""
    selected = _target(target)
    compilation, bundle = _prepare(contract, target=selected)
    try:
        write_review_bundle(bundle, output)
    except ReviewWriteError as error:
        _fail(error)
    typer.echo(f"COMPILED {compilation.contract.metadata.name} ({compilation.contract.version})")
    typer.echo(f"  output: {output}")
    typer.echo(f"  files: {len(bundle.files)} artifacts + manifest.json")
    typer.echo(f"  manifest sha256: {bundle.manifest_sha256}")
    typer.echo(f"  target: {selected}")
    typer.echo("  static validation: passed")
    typer.echo("  safety: generation-only; nothing was executed or deployed")


@app.command("plan")
def plan_command(
    contract: Annotated[Path, typer.Argument(help="DataProduct JSON or YAML file")],
) -> None:
    """Validate and print the deterministic topological execution plan."""
    compilation, _ = _prepare(contract)
    plan = build_execution_plan(compilation.ir)
    typer.echo(f"PLAN {compilation.contract.metadata.name} ({len(plan.steps)} steps)")
    for step in plan.steps:
        dependencies = ", ".join(step.dependencies) or "none"
        typer.echo(f"  {step.position:02d} {step.kind}:{step.name} <- {dependencies}")
    typer.echo(f"  IR sha256: {compilation.ir_digest}")


@app.command("inspect")
def inspect_command(
    manifest: Annotated[Path, typer.Argument(help="Generated compilation manifest")],
) -> None:
    """Verify and summarize a generated compilation manifest."""
    try:
        count, digest = inspect_manifest(manifest)
    except StaticValidationError as error:
        _fail(error)
    typer.echo(f"VALID MANIFEST {manifest}")
    typer.echo(f"  files: {count}")
    typer.echo(f"  sha256: {digest}")


@app.command("inspect-evidence")
def inspect_evidence_command(
    evidence_path: Annotated[Path, typer.Argument(help="Execution evidence JSON")],
) -> None:
    """Validate and summarize deterministic local execution evidence."""
    try:
        evidence = read_execution_evidence(evidence_path)
    except ValueError as error:
        _fail(error)
    typer.echo(f"EVIDENCE {evidence.data_product_id}")
    typer.echo(f"  engine: {evidence.engine} + {evidence.table_format}")
    typer.echo(f"  runs: {len(evidence.runs)}")
    typer.echo(f"  quality rules: {len(evidence.quality)}")
    typer.echo(f"  idempotency: {'passed' if evidence.idempotency_passed else 'failed'}")
    typer.echo(f"  verification: {'passed' if evidence.verification_passed else 'failed'}")
    if not evidence.verification_passed:
        raise typer.Exit(code=1)


@app.command("verify")
def verify_command(
    contract: Annotated[Path, typer.Argument(help="DataProduct JSON or YAML file")],
    suite_path: Annotated[
        Path,
        typer.Option("--suite", help="VerificationSuite JSON or YAML file"),
    ],
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="New or empty verification output directory"),
    ] = Path("build/verification"),
) -> None:
    """Compile and verify one generated workload on local Spark/Iceberg."""
    try:
        suite = parse_verification_suite_file(suite_path)
        compilation, bundle = _prepare(contract, target="spark")
        transformations = {item.id: item for item in compilation.contract.transformations}
        if suite.transformation not in transformations:
            raise ValueError(f"verification transformation does not exist: {suite.transformation}")
        transformation = transformations[suite.transformation]
        fixture_views = {item.view for item in suite.fixtures}
        missing = sorted(set(transformation.inputs) - fixture_views)
        if missing:
            raise ValueError(f"verification suite is missing fixture views: {', '.join(missing)}")
        bundle_path = output / "bundle"
        write_review_bundle(bundle, bundle_path)
        spark_submit = shutil.which("spark-submit")
        if spark_submit is None:
            raise ValueError(
                "spark-submit is unavailable; install the execution extra with "
                "'uv sync --extra execution'"
            )
        generated = bundle_path / "spark" / f"{suite.transformation.replace('-', '_')}.py"
        runner = Path(__file__).resolve().parents[2] / "tools" / "run_reference_pipeline.py"
        if not runner.is_file():
            runner = Path(__file__).resolve().parent / "verification" / "spark_runner.py"
        if not runner.is_file():
            raise ValueError("packaged local verification runner is unavailable")
        warehouse = output / "warehouse"
        command = [
            spark_submit,
            "--master",
            "local[2]",
            "--packages",
            "org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.11.0",
            "--conf",
            "spark.jars.ivy=/tmp/dagwright-ivy",
            "--conf",
            "spark.ui.enabled=false",
            "--conf",
            "spark.sql.extensions=org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions",
            "--conf",
            "spark.sql.catalog.local=org.apache.iceberg.spark.SparkCatalog",
            "--conf",
            "spark.sql.catalog.local.type=hadoop",
            "--conf",
            f"spark.sql.catalog.local.warehouse={warehouse.resolve().as_uri()}",
            "--conf",
            "spark.sql.defaultCatalog=local",
            str(runner),
            "--contract",
            str(bundle_path / "contract.normalized.json"),
            "--generated",
            str(generated),
            "--suite",
            str(suite_path.resolve()),
            "--evidence",
            str(output / "evidence.json"),
            "--warehouse",
            str(warehouse),
        ]
        subprocess.run(command, check=True)
        evidence = read_execution_evidence(output / "evidence.json")
    except (
        VerificationSuiteParseError,
        ReviewWriteError,
        ValueError,
        subprocess.CalledProcessError,
    ) as error:
        _fail(error)
    typer.echo(f"VERIFIED {compilation.contract.metadata.name}")
    typer.echo(f"  suite: {suite.name}")
    typer.echo(f"  evidence: {output / 'evidence.json'}")
    typer.echo(f"  runs: {len(evidence.runs)}")
    typer.echo("  verification: passed")


@app.command("explain")
def explain_command(
    contract: Annotated[Path, typer.Argument(help="DataProduct JSON or YAML file")],
) -> None:
    """Explain the canonical compilation plan without writing files."""
    compilation, bundle = _prepare(contract)
    typer.echo(_explanation(compilation, bundle))


def _prepare(
    path: Path,
    *,
    target: CompilationTarget = "all",
) -> tuple[CompilationResult, ReviewBundle]:
    try:
        contract = parse_contract_file(path)
        sql = load_validated_sql(contract, path.parent)
        compilation = compile_contract(contract)
        adapter = Airflow3Adapter()
        if target in {"airflow", "all"}:
            violations = adapter.validate(compilation.ir)
            if violations:
                raise UnsupportedSemanticsError(adapter.capabilities().name, violations)
        return compilation, build_review_bundle(
            compilation,
            adapter,
            target=target,
            sql_by_transformation=sql,
        )
    except (ContractParseError, CompilerError, UnsupportedSemanticsError, ValueError) as error:
        _fail(error)


def _target(value: str) -> CompilationTarget:
    if value not in {"airflow", "spark", "all"}:
        _fail(ValueError("--target must be one of: airflow, spark, all"))
    return cast(CompilationTarget, value)


def _explanation(compilation: CompilationResult, bundle: ReviewBundle) -> str:
    node_counts = Counter(node.kind for node in compilation.ir.nodes)
    schedule = compilation.ir.execution.schedule or "manual"
    lines = [
        f"DataProduct: {compilation.contract.metadata.name} {compilation.contract.version}",
        f"Contract: {compilation.contract.api_version} sha256:{compilation.contract_digest}",
        f"Canonical IR: {compilation.ir.ir_version} sha256:{compilation.ir_digest}",
        f"Target: Apache Airflow 3 via {bundle.manifest.adapter} {bundle.manifest.adapter_version}",
        f"Schedule: {schedule}",
        f"Graph: {len(compilation.ir.nodes)} nodes, {len(compilation.ir.edges)} edges",
        "Nodes: " + ", ".join(f"{kind}={node_counts[kind]}" for kind in sorted(node_counts)),
        f"Quality gates: {node_counts['quality']} (fail-closed until bound)",
        "Delegated: CDC/source capture, freshness, volume, delivery, late data, watermarks",
        "Review files:",
    ]
    lines.extend(
        f"  {item.path}  sha256:{item.sha256}  {len(item.content)} bytes" for item in bundle.files
    )
    lines.extend(
        [
            f"  manifest.json  sha256:{bundle.manifest_sha256}  {len(bundle.manifest_bytes)} bytes",
            "Safety: generation-only; no artifact was executed or deployed.",
        ]
    )
    return "\n".join(lines)


def _fail(error: Exception) -> Never:
    typer.echo(f"error: {error}", err=True)
    raise typer.Exit(code=1)


if __name__ == "__main__":  # pragma: no cover
    app()
