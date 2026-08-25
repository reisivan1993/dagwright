"""Local environment checks used by the CLI."""

from dataclasses import dataclass
from sys import version_info

MINIMUM_PYTHON = (3, 12)


@dataclass(frozen=True)
class Check:
    """A single doctor check result."""

    name: str
    passed: bool
    detail: str


def python_check(version: tuple[int, int]) -> Check:
    """Check that a Python major/minor pair is supported."""
    required = ".".join(map(str, MINIMUM_PYTHON))
    actual = ".".join(map(str, version))
    return Check(
        name="python",
        passed=version >= MINIMUM_PYTHON,
        detail=f"{actual} (requires >= {required})",
    )


def run_checks() -> tuple[Check, ...]:
    """Run all environment checks."""
    return (python_check((version_info.major, version_info.minor)),)
