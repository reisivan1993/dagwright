"""Regenerate Airflow adapter golden artifacts from the customer example."""

from pathlib import Path

from dagwright.adapters.airflow import Airflow3Adapter
from dagwright.compiler import compile_contract
from dagwright.contracts import parse_contract_file

ROOT = Path(__file__).parents[1]
GOLDEN = ROOT / "tests/golden/airflow"


def main() -> None:
    ir = compile_contract(parse_contract_file(ROOT / "examples/contracts/customer-360.json")).ir
    bundle = Airflow3Adapter().generate(ir)
    GOLDEN.mkdir(parents=True, exist_ok=True)
    (GOLDEN / "customer-360.py").write_bytes(bundle.artifact.content)
    (GOLDEN / "customer-360.manifest.json").write_bytes(bundle.manifest_bytes)


if __name__ == "__main__":
    main()
