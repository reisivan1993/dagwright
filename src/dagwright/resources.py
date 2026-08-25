"""Access published schemas included in installed DAGwright distributions."""

from importlib.resources import files
from pathlib import Path


def schema_path(name: str) -> Path:
    """Return a filesystem path for one known packaged schema."""
    known = {
        "dataproduct-overlay-v1alpha1.json",
        "dataproduct-v1alpha1.json",
        "verification-suite-v1alpha1.json",
    }
    if name not in known:
        raise ValueError(f"unknown DAGwright schema: {name}")
    resource = files("dagwright").joinpath("schemas", name)
    return Path(str(resource))
