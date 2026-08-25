"""Generate and verify the published DataProduct JSON Schema."""

import argparse
import json
from pathlib import Path

from dagwright.contracts.models import DataProduct

SCHEMA_PATH = Path("schemas/dataproduct-v1alpha1.json")


def schema_text() -> str:
    """Return a stable textual representation of the contract schema."""
    schema = DataProduct.model_json_schema(
        by_alias=True,
        mode="validation",
        ref_template="#/$defs/{model}",
    )
    schema["$id"] = "https://dagwright.io/schemas/dataproduct-v1alpha1.json"
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = "DAGwright DataProduct v1alpha1"
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="fail if the published schema is stale"
    )
    parser.add_argument("--output", type=Path, default=SCHEMA_PATH)
    args = parser.parse_args()
    expected = schema_text()
    if args.check:
        if not args.output.exists() or args.output.read_text() != expected:
            parser.error(f"{args.output} is stale; regenerate it with this module")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(expected)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
