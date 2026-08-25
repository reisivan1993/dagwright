import os
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dagwright.cli import app
from dagwright.evidence import ExecutionEvidence, read_execution_evidence

ROOT = Path(__file__).parents[1]
GOLDEN = ROOT / "tests/golden/execution/customer-analytics.evidence.json"
runner = CliRunner()


def test_execution_evidence_golden_proves_checkpoint_invariants() -> None:
    evidence = read_execution_evidence(GOLDEN)

    assert evidence.verification_passed is True
    assert evidence.engine == "apache-spark-3.5"
    assert evidence.table_format == "apache-iceberg"
    assert [run.row_count for run in evidence.runs] == [3, 3]
    assert len({run.output_digest for run in evidence.runs}) == 1
    assert evidence.idempotency_passed is True
    assert evidence.rows_passed is True
    assert evidence.schema_passed is True
    assert evidence.failure_reasons == ()
    assert all(result.passed for result in evidence.quality)
    assert {result.rule_type for result in evidence.quality} == {
        "accepted_values",
        "expression",
        "not_null",
        "referential_integrity",
        "unique",
    }
    assert evidence.quality_negative_control_passed is True
    assert all(result.failure_count > 0 for result in evidence.quality_negative_control)
    assert evidence.negative_controls[0].passed is True


def test_execution_evidence_is_strict() -> None:
    document = read_execution_evidence(GOLDEN).model_dump(mode="json", by_alias=True)
    document["unexpected"] = True

    with pytest.raises(ValueError):
        ExecutionEvidence.model_validate(document)


def test_inspect_evidence_command() -> None:
    result = runner.invoke(app, ["inspect-evidence", str(GOLDEN)])

    assert result.exit_code == 0
    assert "engine: apache-spark-3.5 + apache-iceberg" in result.stdout
    assert "idempotency: passed" in result.stdout
    assert "verification: passed" in result.stdout


def test_failed_evidence_is_valid_and_inspection_exits_nonzero(tmp_path: Path) -> None:
    success = read_execution_evidence(GOLDEN)
    failed = success.model_copy(
        update={
            "rows_passed": False,
            "failure_reasons": ("rows_mismatch",),
            "verification_passed": False,
        }
    )
    path = tmp_path / "failed.json"
    path.write_text(failed.model_dump_json(by_alias=True))

    parsed = read_execution_evidence(path)
    result = runner.invoke(app, ["inspect-evidence", str(path)])

    assert parsed.failure_reasons == ("rows_mismatch",)
    assert result.exit_code == 1
    assert "verification: failed" in result.stdout


@pytest.mark.spark_integration
@pytest.mark.skipif(
    os.environ.get("DAGWRIGHT_RUN_SPARK_TESTS") != "1",
    reason="set DAGWRIGHT_RUN_SPARK_TESTS=1 to run the real Spark/Iceberg integration",
)
def test_real_spark_iceberg_reference_pipeline_matches_evidence_golden() -> None:
    subprocess.run(
        ["make", "verify-reference"],
        cwd=ROOT,
        check=True,
        env={**os.environ, "UV_CACHE_DIR": "/tmp/dagwright-uv-cache"},
    )


@pytest.mark.spark_integration
@pytest.mark.skipif(
    os.environ.get("DAGWRIGHT_RUN_SPARK_TESTS") != "1",
    reason="set DAGWRIGHT_RUN_SPARK_TESTS=1 to run the real Spark/Iceberg integration",
)
def test_real_spark_failure_preserves_diagnostic_evidence(tmp_path: Path) -> None:
    output = tmp_path / "failure"
    completed = subprocess.run(
        [
            "uv",
            "run",
            "--extra",
            "execution",
            "dagwright",
            "verify",
            str(ROOT / "examples/customer-analytics/dataproduct.yaml"),
            "--suite",
            str(ROOT / "examples/customer-analytics/verification-failure.yaml"),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        check=False,
        env={**os.environ, "UV_CACHE_DIR": "/tmp/dagwright-uv-cache"},
    )

    evidence = read_execution_evidence(output / "evidence.json")
    assert completed.returncode == 1
    assert evidence.failure_reasons == ("rows_mismatch",)
    assert evidence.rows_passed is False
    assert evidence.schema_passed is True
    assert evidence.idempotency_passed is True
