"""Engine and orchestrator adapter interfaces."""

from dagwright.adapters.base import (
    AdapterCapabilities,
    ArtifactBundle,
    ArtifactManifest,
    ArtifactMetadata,
    CapabilityViolation,
    GeneratedArtifact,
    GeneratorAdapter,
    LineageMetadata,
    TaskMetadata,
    UnsupportedSemanticsError,
)

__all__ = [
    "AdapterCapabilities",
    "ArtifactBundle",
    "ArtifactManifest",
    "ArtifactMetadata",
    "CapabilityViolation",
    "GeneratedArtifact",
    "GeneratorAdapter",
    "LineageMetadata",
    "TaskMetadata",
    "UnsupportedSemanticsError",
]
