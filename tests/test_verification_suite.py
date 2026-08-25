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
    expectedFailures: [customer-id-not-null]
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


def test_semantics_reject_unused_fixture(tmp_path: Path) -> None:
    from dagwright.contracts import parse_contract_file
    from dagwright.verification import validate_verification_suite

    suite = parse_verification_suite_file(SUITE)
    extra = suite.model_copy(
        update={
            "fixtures": [
                *suite.fixtures,
                suite.fixtures[0].model_copy(update={"view": "unused_view"}),
            ]
        }
    )

    with pytest.raises(ValueError, match="unused fixture views: unused_view"):
        validate_verification_suite(extra, parse_contract_file(CONTRACT), SUITE.parent)


def test_semantics_reject_unknown_negative_rule() -> None:
    from dagwright.contracts import parse_contract_file
    from dagwright.verification import validate_verification_suite

    suite = parse_verification_suite_file(SUITE)
    control = suite.negative_controls[0].model_copy(update={"expected_failures": ["unknown-rule"]})
    changed = suite.model_copy(update={"negative_controls": [control]})

    with pytest.raises(ValueError, match="unknown output quality rules: unknown-rule"):
        validate_verification_suite(changed, parse_contract_file(CONTRACT), SUITE.parent)


def test_semantics_reject_negative_control_that_reuses_baseline_data() -> None:
    from dagwright.contracts import parse_contract_file
    from dagwright.verification import validate_verification_suite

    suite = parse_verification_suite_file(SUITE)
    control = suite.negative_controls[0].model_copy(update={"fixtures": [suite.fixtures[0]]})
    changed = suite.model_copy(update={"negative_controls": [control]})

    with pytest.raises(ValueError, match="does not replace fixture data for: raw_customers"):
        validate_verification_suite(changed, parse_contract_file(CONTRACT), SUITE.parent)
