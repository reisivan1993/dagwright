"""Regenerate the v0.1 end-to-end customer analytics review bundle."""

from pathlib import Path

from dagwright.compiler import compile_contract, load_validated_sql
from dagwright.contracts import parse_contract_file
from dagwright.review import build_review_bundle

ROOT = Path(__file__).parents[1]
CONTRACT = ROOT / "examples/customer-analytics/dataproduct.yaml"
GOLDEN = ROOT / "tests/golden/e2e/customer-analytics"


def main() -> None:
    contract = parse_contract_file(CONTRACT)
    bundle = build_review_bundle(
        compile_contract(contract),
        sql_by_transformation=load_validated_sql(contract, CONTRACT.parent),
    )
    for item in bundle.files:
        destination = GOLDEN / item.path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(item.content)
    (GOLDEN / "manifest.json").write_bytes(bundle.manifest_bytes)


if __name__ == "__main__":
    main()
