"""Project-specific exceptions with concise CLI messages."""


class PipelineError(RuntimeError):
    """Base error for a failed checkpoint-two run."""


class SourceValidationError(PipelineError):
    """Raised when an upstream asset violates its declared contract."""


class DataQualityError(PipelineError):
    """Raised when a transformation would produce invalid analytical data."""
