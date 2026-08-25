import hashlib
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from dagwright.compiler import (
    CycleError,
    MissingReferenceError,
    ReferenceResolutionError,
    SchemaCompatibilityError,
    canonical_bytes,
    compile_contract,
    normalize_contract,
)
from dagwright.compiler.ir import PipelineNode
from dagwright.contracts import DataProduct, parse_contract_file
from tests.test_contract_models import minimal_contract

ROOT = Path(__file__).parents[1]
CUSTOMER = ROOT / "examples/contracts/customer-360.json"


def customer_contract() -> DataProduct:
    return parse_contract_file(CUSTOMER)


def test_defaults_are_resolved_in_canonical_contract() -> None:
    contract = DataProduct.model_validate(minimal_contract())

    payload = canonical_bytes(normalize_contract(contract))

    assert b'"deleteSemantics":"ignore"' in payload
    assert b'"transformations":[]' in payload
    assert b'"quality":[]' in payload
    assert b'"schedule":null' in payload


def test_normalization_is_idempotent() -> None:
    contract = customer_contract()

    once = normalize_contract(contract)
    twice = normalize_contract(once)

    assert once == twice
    assert canonical_bytes(once) == canonical_bytes(twice)


def test_digests_are_sha256_of_exact_canonical_bytes() -> None:
    result = compile_contract(customer_contract())

    assert result.contract_digest == hashlib.sha256(result.contract_bytes).hexdigest()
    assert result.ir_digest == hashlib.sha256(result.ir_bytes).hexdigest()


def test_ir_has_stable_ids_and_dependency_graph() -> None:
    result = compile_contract(customer_contract())
    nodes = {node.stable_id: node for node in result.ir.nodes}

    bronze_id = "urn:dagwright:customer-360:asset:bronze_customers"
    transform_id = "urn:dagwright:customer-360:transformation:build-customer-profile"
    silver_id = "urn:dagwright:customer-360:asset:silver_customers"
    assert result.ir.data_product_id == "urn:dagwright:customer-360:dataproduct"
    assert transform_id in nodes[bronze_id].outputs
    assert nodes[transform_id].inputs == (bronze_id,)
    assert nodes[transform_id].outputs == (silver_id,)
    assert nodes[silver_id].inputs == (transform_id,)
    assert nodes[transform_id].failure_policy == {"action": "fail"}
    assert nodes[transform_id].retry_policy == {"maxAttempts": 1}
    assert nodes[transform_id].resource_hints == {"cpu": 2.0, "memory": "4Gi"}
    assert nodes[transform_id].lineage_metadata == {"provenance": "declared"}
    source_id = "urn:dagwright:customer-360:source:customers-db"
    assert nodes[source_id].security_context == {
        "connectionRef": "secret://production/customers-db"
    }
    assert len(result.ir.nodes) == 6
    assert len(result.ir.edges) == 5


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (lambda data: data["assets"][0].update(source="missing.table"), "source 'missing'"),
        (
            lambda data: data["assets"].append(
                {"name": "derived", "type": "table", "mode": "append", "inputs": ["missing"]}
            ),
            "asset 'missing'",
        ),
        (
            lambda data: data["contracts"].update(
                quality=[
                    {
                        "id": "valid",
                        "type": "not_null",
                        "asset": "missing",
                        "fields": ["id"],
                    }
                ]
            ),
            "asset 'missing'",
        ),
        (
            lambda data: data["assets"][0].update(transformationIds=["missing"]),
            "transformation 'missing'",
        ),
        (
            lambda data: data.update(
                transformations=[
                    {
                        "id": "build",
                        "type": "sql",
                        "inputs": ["missing"],
                        "output": "customers",
                        "sqlRef": "sql/build.sql",
                    }
                ]
            ),
            "asset 'missing'",
        ),
        (
            lambda data: data.update(
                transformations=[
                    {
                        "id": "build",
                        "type": "sql",
                        "inputs": ["customers"],
                        "output": "missing",
                        "sqlRef": "sql/build.sql",
                    }
                ]
            ),
            "asset 'missing'",
        ),
        (
            lambda data: data["contracts"].update(
                quality=[
                    {
                        "id": "foreign-key",
                        "type": "referential_integrity",
                        "asset": "customers",
                        "fields": ["account_id"],
                        "reference": "missing.id",
                    }
                ]
            ),
            "asset 'missing'",
        ),
        (
            lambda data: data["contracts"].update(
                anomalies=[
                    {
                        "id": "volume",
                        "asset": "missing",
                        "metric": "row_count",
                        "method": "relative_change",
                        "threshold": 0.2,
                        "window": "PT1H",
                    }
                ]
            ),
            "asset 'missing'",
        ),
    ],
)
def test_missing_references_are_rejected(
    mutation: Any,
    reason: str,
) -> None:
    data = minimal_contract()
    mutation(data)

    with pytest.raises(MissingReferenceError, match=reason):
        compile_contract(DataProduct.model_validate(data))


def test_cycle_is_rejected_with_stable_id_path() -> None:
    data = minimal_contract()
    data["assets"] = [
        {"name": "first", "type": "table", "mode": "append", "inputs": ["second"]},
        {"name": "second", "type": "table", "mode": "append", "inputs": ["first"]},
    ]

    with pytest.raises(CycleError) as caught:
        compile_contract(DataProduct.model_validate(data))

    message = str(caught.value)
    assert "dependency cycle detected" in message
    assert "urn:dagwright:customer:asset:first" in message
    assert "urn:dagwright:customer:asset:second" in message


def test_orphan_transformation_is_rejected() -> None:
    data = minimal_contract()
    data["transformations"] = [
        {
            "id": "build",
            "type": "sql",
            "inputs": ["customers"],
            "output": "customers",
            "sqlRef": "sql/build.sql",
        }
    ]

    with pytest.raises(MissingReferenceError, match="not referenced by output asset 'customers'"):
        compile_contract(DataProduct.model_validate(data))


def test_transformation_and_output_asset_inputs_must_agree() -> None:
    data = minimal_contract()
    data["assets"].append(
        {
            "name": "profiles",
            "type": "table",
            "mode": "append",
            "inputs": ["customers"],
            "transformationIds": ["build"],
        }
    )
    data["transformations"] = [
        {
            "id": "build",
            "type": "sql",
            "inputs": ["profiles"],
            "output": "profiles",
            "sqlRef": "sql/build.sql",
        }
    ]

    with pytest.raises(ReferenceResolutionError, match="inputs do not match output asset"):
        compile_contract(DataProduct.model_validate(data))


def test_quality_reference_requires_asset_and_field() -> None:
    data = minimal_contract()
    data["contracts"]["quality"] = [
        {
            "id": "foreign-key",
            "type": "referential_integrity",
            "asset": "customers",
            "fields": ["account_id"],
            "reference": "customers",
        }
    ]

    with pytest.raises(ReferenceResolutionError, match=r"must use 'asset\.field' syntax"):
        compile_contract(DataProduct.model_validate(data))


class RejectSchema:
    @property
    def name(self) -> str:
        return "test-schema-hook"

    def check(self, upstream: PipelineNode, downstream: PipelineNode) -> tuple[str, ...]:
        if upstream.kind == "source" and downstream.kind == "asset":
            return ("source field type is incompatible",)
        return ()


def test_schema_compatibility_hook_can_reject_data_edge() -> None:
    with pytest.raises(SchemaCompatibilityError) as caught:
        compile_contract(customer_contract(), schema_hooks=(RejectSchema(),))

    assert "test-schema-hook rejected" in str(caught.value)
    assert "source field type is incompatible" in str(caught.value)


@given(
    reverse_sources=st.booleans(),
    reverse_assets=st.booleans(),
    reverse_rules=st.booleans(),
    explicit_defaults=st.booleans(),
)
def test_semantically_identical_inputs_have_identical_outputs_and_digests(
    reverse_sources: bool,
    reverse_assets: bool,
    reverse_rules: bool,
    explicit_defaults: bool,
) -> None:
    baseline_data = customer_contract().model_dump(mode="json", by_alias=True, exclude_unset=True)
    variant = deepcopy(baseline_data)
    if reverse_sources:
        variant["sources"].reverse()
    if reverse_assets:
        variant["assets"].reverse()
    if reverse_rules:
        variant["contracts"]["quality"].reverse()
        variant["contracts"]["anomalies"].reverse()
    if explicit_defaults:
        bronze = next(asset for asset in variant["assets"] if asset["name"] == "bronze_customers")
        bronze["inputs"] = []
        bronze["primaryKey"] = []
        bronze["transformationIds"] = []
        variant["sources"][0]["capture"]["cursorField"] = None
        variant["assets"][1 if not reverse_assets else 0]["source"] = None

    baseline = compile_contract(customer_contract())
    compiled = compile_contract(DataProduct.model_validate(variant))

    assert compiled.contract_bytes == baseline.contract_bytes
    assert compiled.contract_digest == baseline.contract_digest
    assert compiled.ir_bytes == baseline.ir_bytes
    assert compiled.ir_digest == baseline.ir_digest


@given(size=st.integers(min_value=2, max_value=12))
def test_property_generated_cycles_are_always_rejected(size: int) -> None:
    data = minimal_contract()
    data["assets"] = [
        {
            "name": f"node_{index}",
            "type": "table",
            "mode": "append",
            "inputs": [f"node_{(index + 1) % size}"],
        }
        for index in range(size)
    ]

    with pytest.raises(CycleError):
        compile_contract(DataProduct.model_validate(data))
