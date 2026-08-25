import json
from pathlib import Path
from typing import Any, cast

import pytest
from hypothesis import given
from hypothesis import strategies as st
from typer.testing import CliRunner

from dagwright.cli import app
from dagwright.compiler import compile_contract
from dagwright.contracts import parse_contract_file
from dagwright.overlays import (
    DataProductOverlay,
    OverlayError,
    OverlayPatch,
    apply_overlays,
    parse_overlay_file,
)

ROOT = Path(__file__).parents[1]
CONTRACT = ROOT / "examples/customer-analytics/dataproduct.yaml"
EXAMPLE = ROOT / "examples/customer-analytics/development.overlay.yaml"
GOLDEN = ROOT / "tests/golden/overlays"
runner = CliRunner()


def overlay(name: str, path: str, value: Any) -> DataProductOverlay:
    return DataProductOverlay(
        api_version="dagwright.io/v1alpha1",
        kind="DataProductOverlay",
        name=name,
        patches=[OverlayPatch(path=path, value=value)],
    )


def test_example_overlay_changes_environment_without_mutating_base() -> None:
    base = parse_contract_file(CONTRACT)
    result = apply_overlays(base, [parse_overlay_file(EXAMPLE)])

    assert base.metadata.environment == "production"
    assert result.metadata.environment == "development"
    assert result.execution.schedule is None
    assert result.execution.resources is not None
    assert result.execution.resources.cpu == 1.0
    assert result.sources[0].connection_ref.startswith("secret://development/")


def test_example_overlay_effective_contract_and_digests_match_golden() -> None:
    base = parse_contract_file(CONTRACT)
    result = compile_contract(apply_overlays(base, [parse_overlay_file(EXAMPLE)]))
    digests = json.loads((GOLDEN / "development.digests.json").read_text())

    assert result.contract_bytes == (GOLDEN / "development.contract.json").read_bytes()
    assert result.contract_digest == digests["contractSha256"]
    assert result.ir_digest == digests["irSha256"]


@given(reverse=st.booleans())
def test_disjoint_overlay_order_cannot_change_compilation(reverse: bool) -> None:
    base = parse_contract_file(CONTRACT)
    overlays = [
        overlay("environment", "/metadata/environment", "test"),
        overlay("schedule", "/execution/schedule", None),
    ]
    if reverse:
        overlays.reverse()

    result = compile_contract(apply_overlays(base, overlays))
    expected = compile_contract(apply_overlays(base, list(reversed(overlays))))

    assert result.contract_bytes == expected.contract_bytes
    assert result.ir_bytes == expected.ir_bytes


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("/metadata/environment", "/metadata/environment"),
        ("/execution/resources", "/execution/resources/cpu"),
    ],
)
def test_overlapping_patches_fail_with_both_owners(first: str, second: str) -> None:
    with pytest.raises(OverlayError, match=r"overlapping overlay patches alpha:.*beta:"):
        apply_overlays(
            parse_contract_file(CONTRACT),
            [overlay("alpha", first, "test"), overlay("beta", second, "test")],
        )


def test_missing_path_and_invalid_result_are_diagnostic() -> None:
    base = parse_contract_file(CONTRACT)
    with pytest.raises(OverlayError, match="path does not exist"):
        apply_overlays(base, [overlay("missing", "/metadata/unknown", "test")])
    with pytest.raises(OverlayError, match="produce an invalid DataProduct"):
        apply_overlays(base, [overlay("invalid", "/metadata/environment", "NOT VALID")])


@pytest.mark.parametrize("path", ["/apiVersion", "/version", "/metadata", "/metadata/name"])
def test_overlay_cannot_replace_contract_identity(path: str) -> None:
    with pytest.raises(ValueError, match="may not replace contract identity"):
        overlay("identity", path, "changed")


def test_cli_compile_applies_overlay_to_normalized_contract(tmp_path: Path) -> None:
    output = tmp_path / "development"
    result = runner.invoke(
        app,
        [
            "compile",
            str(CONTRACT),
            "--overlay",
            str(EXAMPLE),
            "--target",
            "spark",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0
    normalized = cast(dict[str, Any], json.loads((output / "contract.normalized.json").read_text()))
    assert normalized["metadata"]["environment"] == "development"
    assert normalized["execution"]["schedule"] is None


def test_cli_reports_cross_overlay_conflict() -> None:
    result = runner.invoke(
        app,
        ["validate", str(CONTRACT), "--overlay", str(EXAMPLE), "--overlay", str(EXAMPLE)],
    )

    assert result.exit_code == 1
    assert "duplicate overlay names: development" in result.stderr


@pytest.mark.parametrize("command", ["validate", "plan", "explain"])
def test_read_only_cli_workflows_accept_overlay(command: str) -> None:
    result = runner.invoke(app, [command, str(CONTRACT), "--overlay", str(EXAMPLE)])

    assert result.exit_code == 0
