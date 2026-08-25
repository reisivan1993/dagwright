import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any, cast

import pytest
from typer.testing import CliRunner

from dagwright.cli import app

ROOT = Path(__file__).parents[1]
CONTRACT = ROOT / "examples/customer-analytics/dataproduct.yaml"
GOLDEN = ROOT / "tests/golden/e2e/customer-analytics"
runner = CliRunner()


def files(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_v01_customer_analytics_end_to_end_golden(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    validate_result = runner.invoke(app, ["validate", str(CONTRACT)])
    explain_result = runner.invoke(app, ["explain", str(CONTRACT)])
    first_output = tmp_path / "first"
    second_output = tmp_path / "second"
    first_compile = runner.invoke(app, ["compile", str(CONTRACT), "--output", str(first_output)])
    second_compile = runner.invoke(app, ["compile", str(CONTRACT), "--output", str(second_output)])

    assert validate_result.exit_code == 0
    assert validate_result.stdout.startswith("VALID customer-analytics (1.0.0)\n")
    assert "adapter: airflow3+spark-iceberg (supported, generation-only)" in validate_result.stdout
    assert explain_result.exit_code == 0
    assert "Graph: 12 nodes, 11 edges" in explain_result.stdout
    assert "Quality gates: 5 (fail-closed until bound)" in explain_result.stdout
    assert "Safety: generation-only; no artifact was executed or deployed." in explain_result.stdout
    assert first_compile.exit_code == second_compile.exit_code == 0
    assert "9 artifacts + manifest.json" in first_compile.stdout
    assert "static validation: passed" in first_compile.stdout
    assert "nothing was executed or deployed" in first_compile.stdout
    assert files(first_output) == files(second_output) == files(GOLDEN)

    monkeypatch.setenv("AIRFLOW_HOME", str(tmp_path / "airflow-home"))
    dag_path = first_output / "dags/dagwright__customer_analytics.py"
    spec = importlib.util.spec_from_file_location("generated_customer_analytics", dag_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.dag.dag_id == "dagwright__customer_analytics"
    assert len(module.dag.task_dict) == 12


def test_compilation_manifest_digests_every_emitted_artifact(tmp_path: Path) -> None:
    output = tmp_path / "review"

    result = runner.invoke(app, ["compile", str(CONTRACT), "-o", str(output)])

    assert result.exit_code == 0
    manifest = cast(dict[str, Any], json.loads((output / "manifest.json").read_text()))
    assert manifest["apiVersion"] == "dagwright.io/compilation-manifest/v1alpha1"
    assert manifest["compilerVersion"] == "0.1.0"
    assert manifest["generationOnly"] is True
    assert len(manifest["files"]) == 9
    for metadata in manifest["files"]:
        content = (output / metadata["path"]).read_bytes()
        assert metadata["size"] == len(content)
        assert metadata["sha256"] == hashlib.sha256(content).hexdigest()


def test_plan_targeted_compile_and_inspect_workflow(tmp_path: Path) -> None:
    plan = runner.invoke(app, ["plan", str(CONTRACT)])
    output = tmp_path / "airflow"
    compile_result = runner.invoke(
        app,
        ["compile", str(CONTRACT), "--target", "airflow", "-o", str(output)],
    )
    inspect = runner.invoke(app, ["inspect", str(output / "manifest.json")])

    assert plan.exit_code == 0
    assert plan.stdout.startswith("PLAN customer-analytics (12 steps)\n")
    assert compile_result.exit_code == 0
    assert "target: airflow" in compile_result.stdout
    assert not (output / "spark").exists()
    assert inspect.exit_code == 0
    assert "VALID MANIFEST" in inspect.stdout
    assert "files: 6" in inspect.stdout


def test_compile_rejects_invalid_referenced_sql(tmp_path: Path) -> None:
    contract = tmp_path / "dataproduct.yaml"
    contract.write_text(CONTRACT.read_text().replace("sql/customer_engagement.sql", "broken.sql"))
    (tmp_path / "broken.sql").write_text("SELECT FROM")

    result = runner.invoke(app, ["validate", str(contract)])

    assert result.exit_code == 1
    assert "invalid Spark SQL" in result.stderr


def test_compile_refuses_nonempty_output_directory(tmp_path: Path) -> None:
    output = tmp_path / "review"
    output.mkdir()
    (output / "belongs-to-user.txt").write_text("preserve me")

    result = runner.invoke(app, ["compile", str(CONTRACT), "-o", str(output)])

    assert result.exit_code == 1
    assert "output directory must be absent or empty" in result.stderr
    assert (output / "belongs-to-user.txt").read_text() == "preserve me"


def test_validate_reports_human_readable_contract_error(tmp_path: Path) -> None:
    contract = tmp_path / "invalid.yaml"
    contract.write_text("apiVersion: dagwright.io/v1alpha1\nkind: DataProduct\nversion: invalid\n")

    result = runner.invoke(app, ["validate", str(contract)])

    assert result.exit_code == 1
    assert result.stderr.startswith(f"error: {contract}:")
    assert "$.version: String should match pattern" in result.stderr
    assert "$.metadata: Field required" in result.stderr
