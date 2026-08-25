from pathlib import Path

import pytest
from typer.testing import CliRunner

from dagwright.cli import app
from dagwright.verification import VerificationSuiteParseError, parse_verification_suite_file

ROOT = Path(__file__).parents[1]
SUITE = ROOT / "examples/customer-analytics/verification.yaml"
CONTRACT = ROOT / "examples/customer-analytics/dataproduct.yaml"
runner = CliRunner()


def test_parses_reference_suite() -> None:
    suite = parse_verification_suite_file(SUITE)

    assert suite.api_version == "dagwright.io/verification-suite/v1alpha1"
    assert suite.transformation == "build-customer-engagement"
    assert suite.attempts == 2
    assert {fixture.view for fixture in suite.fixtures} == {
        "raw_customers",
        "raw_customer_events",
    }


def test_rejects_missing_fixture_file(tmp_path: Path) -> None:
    path = tmp_path / "suite.yaml"
    path.write_text(
        """apiVersion: dagwright.io/verification-suite/v1alpha1
kind: VerificationSuite
name: broken
transformation: build-customer-engagement
fixtures:
  - view: raw_customers
    path: missing.json
expected:
  rows: missing.json
  schema: missing.json
  orderBy: [customer_id]
negativeControls:
  - name: invalid
    fixtures:
      - view: raw_customers
        path: missing.json
attempts: 2
"""
    )

    with pytest.raises(VerificationSuiteParseError, match="does not exist"):
        parse_verification_suite_file(path)


def test_verify_reports_missing_execution_extra(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("dagwright.cli.shutil.which", lambda _: None)

    result = runner.invoke(
        app,
        ["verify", str(CONTRACT), "--suite", str(SUITE), "--output", str(tmp_path / "run")],
    )

    assert result.exit_code == 1
    assert "spark-submit is unavailable" in result.stderr
