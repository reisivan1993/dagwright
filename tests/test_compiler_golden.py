import json
from pathlib import Path
from typing import cast

from dagwright.compiler import compile_contract
from dagwright.contracts import parse_contract_file

ROOT = Path(__file__).parents[1]
GOLDEN = ROOT / "tests/golden"


def test_customer_contract_and_ir_match_golden_files() -> None:
    result = compile_contract(parse_contract_file(ROOT / "examples/contracts/customer-360.json"))
    digests = cast(dict[str, str], json.loads((GOLDEN / "customer-360.digests.json").read_text()))

    assert result.contract_bytes == (GOLDEN / "customer-360.contract.json").read_bytes()
    assert result.ir_bytes == (GOLDEN / "customer-360.ir.json").read_bytes()
    assert result.contract_digest == digests["contractSha256"]
    assert result.ir_digest == digests["irSha256"]
