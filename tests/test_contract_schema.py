import json
from pathlib import Path
from typing import Any, cast

import jsonschema
import pytest

from dagwright.contracts.schema import SCHEMA_PATH, schema_text

ROOT = Path(__file__).parents[1]
EXAMPLE = ROOT / "examples/contracts/customer-360.json"
INVALID = ROOT / "tests/fixtures/contracts/invalid"


def load_json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text()))


def test_published_schema_is_current_and_deterministic() -> None:
    first = schema_text()
    second = schema_text()

    assert first == second
    assert (ROOT / SCHEMA_PATH).read_text() == first


def test_published_schema_is_valid_draft_2020_12() -> None:
    jsonschema.Draft202012Validator.check_schema(json.loads(schema_text()))


def test_customer_example_satisfies_published_schema() -> None:
    jsonschema.validate(load_json(EXAMPLE), json.loads(schema_text()))


@pytest.mark.parametrize(
    "fixture",
    [
        INVALID / "bad-version.json",
        INVALID / "unknown-field.json",
        INVALID / "unowned-extension.json",
    ],
    ids=lambda path: path.stem,
)
def test_invalid_fixture_fails_published_schema(fixture: Path) -> None:
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(load_json(fixture), json.loads(schema_text()))
