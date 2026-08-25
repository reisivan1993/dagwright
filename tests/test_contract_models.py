import json
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from dagwright.contracts import DataProduct

ROOT = Path(__file__).parents[1]
EXAMPLE = ROOT / "examples/contracts/customer-360.json"
INVALID = ROOT / "tests/fixtures/contracts/invalid"


def load_json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text()))


def minimal_contract() -> dict[str, Any]:
    return {
        "apiVersion": "dagwright.io/v1alpha1",
        "kind": "DataProduct",
        "version": "1.0.0",
        "metadata": {"name": "customer", "owner": "data", "environment": "test"},
        "sources": [
            {
                "name": "source",
                "type": "postgres",
                "connectionRef": "secret://test/db",
                "capture": {"mode": "cdc"},
            }
        ],
        "assets": [{"name": "customers", "type": "table", "mode": "append", "source": "db.table"}],
        "contracts": {"delivery": {"duplicates": "possible", "ordering": "none"}},
        "execution": {
            "transformEngine": "spark",
            "orchestrator": "airflow",
            "targetCatalog": "iceberg",
        },
        "governance": {
            "dataClassification": "internal",
            "productionRepairPolicy": "disabled",
        },
    }


def test_customer_example_validates() -> None:
    contract = DataProduct.model_validate(load_json(EXAMPLE))

    assert contract.metadata.name == "customer-360"
    assert contract.version == "0.1.0-alpha.1"
    assert contract.model_extra == {"x-acme.io/lineage": {"externalId": "customer-360"}}
    assert contract.metadata.model_extra == {"x-acme.catalog": {"tier": "gold"}}


@pytest.mark.parametrize(
    ("filename", "reason"),
    [
        ("unknown-field.json", "unknown field(s): 'unexpected'"),
        ("bad-version.json", "String should match pattern"),
        ("unowned-extension.json", "unknown field(s): 'custom'"),
        ("bad-asset-origin.json", "asset requires exactly one origin"),
        ("bad-transformation.json", "sql transformation requires sqlRef"),
        ("bad-volume-range.json", "min must be less than or equal to max"),
    ],
)
def test_invalid_fixtures_fail_for_expected_reason(filename: str, reason: str) -> None:
    with pytest.raises(ValidationError) as caught:
        DataProduct.model_validate(load_json(INVALID / filename))

    assert reason in str(caught.value)


def test_unknown_nested_field_has_useful_location() -> None:
    data = minimal_contract()
    data["sources"][0]["capture"]["typo"] = True

    with pytest.raises(ValidationError) as caught:
        DataProduct.model_validate(data)

    error = caught.value.errors()[0]
    assert error["loc"] == ("sources", 0, "capture")
    assert "custom fields must use a namespaced 'x-' key" in error["msg"]


def test_strict_mode_rejects_coercion() -> None:
    data = minimal_contract()
    data["contracts"]["volume"] = {"expectedRowsPerHour": {"min": "1", "max": 2}}

    with pytest.raises(ValidationError, match="valid integer"):
        DataProduct.model_validate(data)


@pytest.mark.parametrize(
    ("rule", "message"),
    [
        (
            {"id": "allowed", "type": "accepted_values", "fields": ["status"]},
            "requires non-empty values",
        ),
        (
            {"id": "positive", "type": "expression", "fields": ["amount"]},
            "requires expression",
        ),
    ],
)
def test_parameterized_quality_rules_require_their_parameter(
    rule: dict[str, Any], message: str
) -> None:
    data = minimal_contract()
    data["contracts"]["quality"] = [{**rule, "asset": "customers"}]

    with pytest.raises(ValidationError, match=message):
        DataProduct.model_validate(data)


def test_round_trip_preserves_extensions_and_aliases() -> None:
    original = DataProduct.model_validate(load_json(EXAMPLE))

    restored = DataProduct.model_validate_json(original.model_dump_json(by_alias=True))

    assert restored == original
    assert restored.model_dump(mode="json", by_alias=True) == original.model_dump(
        mode="json", by_alias=True
    )


@given(
    major=st.integers(min_value=0, max_value=999),
    minor=st.integers(min_value=0, max_value=999),
    patch=st.integers(min_value=0, max_value=999),
    extension_value=st.one_of(st.none(), st.booleans(), st.integers(), st.text()),
)
def test_valid_semver_and_extension_values_round_trip(
    major: int,
    minor: int,
    patch: int,
    extension_value: object,
) -> None:
    data = deepcopy(minimal_contract())
    data["version"] = f"{major}.{minor}.{patch}"
    data["x-tests.example"] = extension_value

    contract = DataProduct.model_validate(data)
    dumped = contract.model_dump(mode="json", by_alias=True)

    assert dumped["version"] == data["version"]
    assert dumped["x-tests.example"] == extension_value
    assert DataProduct.model_validate(dumped) == contract
