"""Publish the VerificationSuite v1alpha1 JSON Schema."""

import argparse
import json
from pathlib import Path

from dagwright.verification.models import VerificationSuite

SCHEMA_PATH = Path("schemas/verification-suite-v1alpha1.json")


def schema_bytes() -> bytes:
    """Return deterministic JSON Schema bytes."""
    document = VerificationSuite.model_json_schema(by_alias=True)
    return json.dumps(document, indent=2, sort_keys=True).encode() + b"\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = schema_bytes()
    if args.check:
        return 0 if SCHEMA_PATH.is_file() and SCHEMA_PATH.read_bytes() == expected else 1
    SCHEMA_PATH.write_bytes(expected)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
