"""Default resolution, normalization, canonical serialization, and hashing."""

import hashlib
import json
from typing import Any

from pydantic import BaseModel

from dagwright.contracts.models import ContractExpectations, DataProduct


def normalize_contract(contract: DataProduct) -> DataProduct:
    """Return the deterministic contract representation for semantic processing."""
    contracts = contract.contracts.model_copy(
        update={
            "quality": sorted(contract.contracts.quality, key=lambda rule: rule.id),
            "anomalies": sorted(contract.contracts.anomalies, key=lambda rule: rule.id),
        }
    )
    assert isinstance(contracts, ContractExpectations)
    return contract.model_copy(
        update={
            "sources": sorted(contract.sources, key=lambda source: source.name),
            "assets": sorted(contract.assets, key=lambda asset: asset.name),
            "transformations": sorted(
                contract.transformations,
                key=lambda transformation: transformation.id,
            ),
            "contracts": contracts,
        }
    )


def canonical_bytes(value: BaseModel) -> bytes:
    """Serialize a model as canonical UTF-8 JSON with all resolved defaults."""
    payload: Any = value.model_dump(mode="json", by_alias=True, exclude_none=False)
    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def canonical_digest(value: BaseModel) -> str:
    """Return the lowercase SHA-256 digest of canonical model bytes."""
    return hashlib.sha256(canonical_bytes(value)).hexdigest()
