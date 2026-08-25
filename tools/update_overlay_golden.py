"""Regenerate deterministic environment-overlay golden files."""

import json
from pathlib import Path

from dagwright.compiler import compile_contract
from dagwright.contracts import parse_contract_file
from dagwright.overlays import apply_overlays, parse_overlay_file

ROOT = Path(__file__).parents[1]
OUTPUT = ROOT / "tests/golden/overlays"


def main() -> None:
    contract = parse_contract_file(ROOT / "examples/customer-analytics/dataproduct.yaml")
    overlay = parse_overlay_file(ROOT / "examples/customer-analytics/development.overlay.yaml")
    result = compile_contract(apply_overlays(contract, [overlay]))
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "development.contract.json").write_bytes(result.contract_bytes)
    digests = {
        "contractSha256": result.contract_digest,
        "irSha256": result.ir_digest,
    }
    (OUTPUT / "development.digests.json").write_text(
        json.dumps(digests, indent=2, sort_keys=True) + "\n"
    )


if __name__ == "__main__":
    main()
