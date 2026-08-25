"""Typed deterministic compiler errors."""


class CompilerError(ValueError):
    """Base class for contract compilation failures."""


class MissingReferenceError(CompilerError):
    """Raised when a contract reference cannot be resolved."""


class ReferenceResolutionError(CompilerError):
    """Raised when individually valid references form an inconsistent binding."""


class CycleError(CompilerError):
    """Raised when the data dependency graph contains a cycle."""


class SchemaCompatibilityError(CompilerError):
    """Raised when a registered compatibility hook rejects an edge."""


class SQLValidationError(CompilerError):
    """Raised when a declared SQL implementation cannot be resolved or parsed."""
