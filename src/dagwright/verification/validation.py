"""Semantic validation for VerificationSuite and DataProduct pairs."""

import json
from pathlib import Path
from typing import Any

from dagwright.contracts.models import DataProduct
from dagwright.verification.models import VerificationSuite


class VerificationSuiteSemanticError(ValueError):
    """Raised when a structurally valid suite cannot verify its DataProduct."""


def validate_verification_suite(
    suite: VerificationSuite, contract: DataProduct, suite_root: Path
) -> None:
    """Reject ambiguous suite bindings before starting an execution engine."""
    transformations = {item.id: item for item in contract.transformations}
    if suite.transformation not in transformations:
        raise VerificationSuiteSemanticError(
            f"verification transformation does not exist: {suite.transformation}"
        )
    transformation = transformations[suite.transformation]
    baseline_paths = {item.view: item.path for item in suite.fixtures}
    fixture_views = {item.view for item in suite.fixtures}
    required_views = set(transformation.inputs)
    missing = sorted(required_views - fixture_views)
    unused = sorted(fixture_views - required_views)
    if missing:
        raise VerificationSuiteSemanticError(
            f"verification suite is missing fixture views: {', '.join(missing)}"
        )
    if unused:
        raise VerificationSuiteSemanticError(
            f"verification suite has unused fixture views: {', '.join(unused)}"
        )

    output_rules = {
        item.id for item in contract.contracts.quality if item.asset == transformation.output
    }
    for control in suite.negative_controls:
        replacements = {item.view for item in control.fixtures}
        unknown_views = sorted(replacements - required_views)
        if unknown_views:
            raise VerificationSuiteSemanticError(
                f"negative control {control.name!r} replaces unknown views: "
                f"{', '.join(unknown_views)}"
            )
        unchanged = sorted(
            item.view for item in control.fixtures if baseline_paths[item.view] == item.path
        )
        if unchanged:
            raise VerificationSuiteSemanticError(
                f"negative control {control.name!r} does not replace fixture data for: "
                f"{', '.join(unchanged)}"
            )
        unknown_rules = sorted(set(control.expected_failures) - output_rules)
        if unknown_rules:
            raise VerificationSuiteSemanticError(
                f"negative control {control.name!r} names unknown output quality rules: "
                f"{', '.join(unknown_rules)}"
            )

    schema = _read_json(suite_root / suite.expected.schema_path, "expected schema")
    rows = _read_json(suite_root / suite.expected.rows, "expected rows")
    if not isinstance(schema, list) or not all(
        isinstance(field, dict) and isinstance(field.get("name"), str) for field in schema
    ):
        raise VerificationSuiteSemanticError("expected schema must be a list of named fields")
    schema_fields = {field["name"] for field in schema}
    unknown_order = sorted(set(suite.expected.order_by) - schema_fields)
    if unknown_order:
        raise VerificationSuiteSemanticError(
            f"expected orderBy fields are absent from expected schema: {', '.join(unknown_order)}"
        )
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise VerificationSuiteSemanticError("expected rows must be a list of objects")
    for index, row in enumerate(rows):
        missing_order = sorted(set(suite.expected.order_by) - row.keys())
        if missing_order:
            raise VerificationSuiteSemanticError(
                f"expected row {index} is missing orderBy fields: {', '.join(missing_order)}"
            )


def _read_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise VerificationSuiteSemanticError(f"invalid {label} {path}: {error}") from error
