"""JSON/YAML parsing for VerificationSuite documents."""

import json
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from dagwright.verification.models import VerificationSuite


class VerificationSuiteParseError(ValueError):
    """A verification-suite syntax or validation error."""


def parse_verification_suite_file(path: Path) -> VerificationSuite:
    """Read and strictly validate a JSON or YAML verification suite."""
    if path.suffix.lower() not in {".json", ".yaml", ".yml"}:
        raise VerificationSuiteParseError(
            f"{path}: unsupported verification suite format; expected JSON or YAML"
        )
    try:
        text = path.read_text()
        raw: Any = json.loads(text) if path.suffix.lower() == ".json" else yaml.safe_load(text)
        suite = VerificationSuite.model_validate(raw, strict=True)
    except (OSError, ValueError, yaml.YAMLError, ValidationError) as error:
        raise VerificationSuiteParseError(f"invalid verification suite {path}: {error}") from error
    _require_files(path.parent, suite)
    return suite


def _require_files(root: Path, suite: VerificationSuite) -> None:
    resolved_root = root.resolve()
    paths = [suite.expected.rows, suite.expected.schema_path]
    paths.extend(item.path for item in suite.fixtures)
    paths.extend(item.path for control in suite.negative_controls for item in control.fixtures)
    for relative in paths:
        candidate = root.joinpath(*relative.split("/")).resolve()
        if not candidate.is_relative_to(resolved_root):
            raise VerificationSuiteParseError(
                f"verification fixture escapes suite directory: {relative}"
            )
        if not candidate.is_file():
            raise VerificationSuiteParseError(f"verification fixture does not exist: {candidate}")
