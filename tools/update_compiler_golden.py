"""Regenerate checkpoint-2 golden compiler artifacts from the customer example."""

import json
from pathlib import Path

from dagwright.compiler import compile_contract
from dagwright.contracts import parse_contract_file

ROOT = Path(__file__).parents[1]
GOLDEN = ROOT / "tests/golden"


def main() -> None:
    result = compile_contract(parse_contract_file(ROOT / "examples/contracts/customer-360.json"))
    GOLDEN.mkdir(parents=True, exist_ok=True)
    (GOLDEN / "customer-360.contract.json").write_bytes(result.contract_bytes)
    (GOLDEN / "customer-360.ir.json").write_bytes(result.ir_bytes)
    (GOLDEN / "customer-360.digests.json").write_text(
        json.dumps(
            {
                "contractSha256": result.contract_digest,
                "irSha256": result.ir_digest,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
