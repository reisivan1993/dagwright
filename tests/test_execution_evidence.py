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
    assert all(result.passed for result in evidence.quality)
    assert evidence.quality_negative_control_passed is True
    assert all(result.failure_count == 1 for result in evidence.quality_negative_control)


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
