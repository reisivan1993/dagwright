"""Static SQL reference resolution and SQLGlot validation."""

from pathlib import Path

import sqlglot
from sqlglot.errors import ParseError

from dagwright.compiler.errors import SQLValidationError
from dagwright.contracts.models import DataProduct


def load_validated_sql(contract: DataProduct, base_directory: Path) -> dict[str, str]:
    """Load declared SQL files without escaping the contract directory and validate syntax."""
    root = base_directory.resolve()
    validated: dict[str, str] = {}
    for transformation in contract.transformations:
        if transformation.type != "sql" or transformation.sql_ref is None:
            continue
        candidate = (root / transformation.sql_ref).resolve()
        if not candidate.is_relative_to(root):
            raise SQLValidationError(
                f"transformations.{transformation.id}.sqlRef escapes the contract directory"
            )
        try:
            source = candidate.read_text(encoding="utf-8")
        except OSError as error:
            raise SQLValidationError(
                f"transformations.{transformation.id}.sqlRef cannot be read: {candidate}"
            ) from error
        try:
            statements = sqlglot.parse(source, read="spark")
        except ParseError as error:
            raise SQLValidationError(
                f"transformations.{transformation.id}.sqlRef is invalid Spark SQL: {error}"
            ) from error
        if len(statements) != 1 or statements[0] is None:
            raise SQLValidationError(
                f"transformations.{transformation.id}.sqlRef must contain exactly one statement"
            )
        validated[transformation.id] = statements[0].sql(dialect="spark", pretty=True)
    return validated
