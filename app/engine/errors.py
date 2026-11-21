from typing import Any, Optional


class EngineError(Exception):
    """Domain error raised by the pure game engine with a machine-readable error_code."""

    def __init__(
        self,
        error_code: str,
        message: str,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.details = details or {}
