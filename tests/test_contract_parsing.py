from pathlib import Path

import pytest

from dagwright.compiler import canonical_bytes, normalize_contract
from dagwright.contracts import ContractParseError, parse_contract, parse_contract_file

ROOT = Path(__file__).parents[1]


def test_json_and_yaml_parse_to_same_semantic_contract() -> None:
    json_contract = parse_contract_file(ROOT / "examples/contracts/customer-360.json")
    yaml_contract = parse_contract_file(ROOT / "tests/fixtures/contracts/customer-360.yaml")

    assert canonical_bytes(normalize_contract(json_contract)) == canonical_bytes(
        normalize_contract(yaml_contract)
    )


def test_json_syntax_error_reports_source_line_and_column() -> None:
    with pytest.raises(ContractParseError) as caught:
        parse_contract('{\n  "kind": }', format="json", source="broken.json")

    assert str(caught.value).startswith("broken.json:2:")
    assert "Expecting value" in str(caught.value)


def test_yaml_duplicate_key_reports_position() -> None:
    text = "apiVersion: dagwright.io/v1alpha1\napiVersion: duplicate\n"

    with pytest.raises(ContractParseError) as caught:
        parse_contract(text, format="yaml", source="duplicate.yaml")

    assert str(caught.value).startswith("duplicate.yaml:2:1")
    assert "duplicate key 'apiVersion'" in str(caught.value)


def test_json_duplicate_key_is_rejected() -> None:
    with pytest.raises(ContractParseError, match="duplicate key 'kind'"):
        parse_contract('{"kind":"DataProduct","kind":"Other"}', format="json")


def test_validation_error_includes_object_path() -> None:
    text = """
apiVersion: dagwright.io/v1alpha1
kind: DataProduct
version: not-semver
"""

    with pytest.raises(ContractParseError) as caught:
        parse_contract(text, format="yaml", source="invalid.yaml")

    message = str(caught.value)
    assert "invalid.yaml:" in message
    assert "$.version: String should match pattern" in message
    assert "$.metadata: Field required" in message


def test_file_extension_must_be_supported(tmp_path: Path) -> None:
    path = tmp_path / "contract.txt"
    path.write_text("{}")

    with pytest.raises(ContractParseError, match=r"expected \.json, \.yaml, or \.yml"):
        parse_contract_file(path)
