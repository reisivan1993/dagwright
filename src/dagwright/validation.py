"""Static validation of generated DAGwright artifacts."""

import ast
import hashlib
import json
from pathlib import Path
from typing import Any, cast


class StaticValidationError(ValueError):
    """Raised when generated artifacts fail deterministic static checks."""


def validate_bundle_files(files: dict[str, bytes]) -> None:
    """Parse generated Python and verify manifest-addressed file digests."""
    for path, content in files.items():
        if path.endswith(".py"):
            try:
                ast.parse(content, filename=path)
            except SyntaxError as error:
                raise StaticValidationError(f"invalid generated Python {path}: {error}") from error


def inspect_manifest(path: Path) -> tuple[int, str]:
    """Verify a compilation manifest and return its file count and digest."""
    try:
        raw = path.read_bytes()
        document = cast(dict[str, Any], json.loads(raw))
        entries = cast(list[dict[str, Any]], document["files"])
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise StaticValidationError(f"cannot read compilation manifest {path}: {error}") from error
    for entry in entries:
        relative = Path(cast(str, entry["path"]))
        if relative.is_absolute() or ".." in relative.parts:
            raise StaticValidationError(f"unsafe manifest path: {relative}")
        try:
            content = (path.parent / relative).read_bytes()
        except OSError as error:
            raise StaticValidationError(f"missing manifest artifact: {relative}") from error
        digest = hashlib.sha256(content).hexdigest()
        if digest != entry["sha256"] or len(content) != entry["size"]:
            raise StaticValidationError(f"artifact integrity check failed: {relative}")
    return len(entries), hashlib.sha256(raw).hexdigest()
