"""
Application-wide error types.

All errors raised by services/providers eventually surface through the
FastAPI exception handler in app/main.py as:

{
    "error": {
        "code": "VIDEO_PROVIDER_ERROR",
        "message": "Human readable message",
        "retryable": true
    }
}
"""
from __future__ import annotations

from typing import Any, Optional


class AppError(Exception):
    """Base application error carrying a stable machine-readable code."""

    code: str = "INTERNAL_ERROR"
    status_code: int = 500
    retryable: bool = False

    def __init__(
        self,
        message: str,
        *,
        code: Optional[str] = None,
        status_code: Optional[int] = None,
        retryable: Optional[bool] = None,
        details: Optional[dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code
        if retryable is not None:
            self.retryable = retryable
        self.details = details or {}

    def to_dict(self) -> dict:
        body = {
            "error": {
                "code": self.code,
                "message": self.message,
                "retryable": self.retryable,
            }
        }
        if self.details:
            body["error"]["details"] = self.details
        return body


class NotFoundError(AppError):
    code = "NOT_FOUND"
    status_code = 404
    retryable = False


class ValidationAppError(AppError):
    code = "VALIDATION_ERROR"
    status_code = 422
    retryable = False


class RateLimitError(AppError):
    code = "RATE_LIMIT_EXCEEDED"
    status_code = 429
    retryable = True


class ProviderAuthError(AppError):
    code = "PROVIDER_AUTH_ERROR"
    status_code = 401
    retryable = False


class ProviderRateLimitError(AppError):
    code = "PROVIDER_RATE_LIMIT"
    status_code = 429
    retryable = True


class ProviderTimeoutError(AppError):
    code = "PROVIDER_TIMEOUT"
    status_code = 504
    retryable = True


class ProviderUnavailableError(AppError):
    code = "PROVIDER_UNAVAILABLE"
    status_code = 503
    retryable = True


class InvalidPromptError(AppError):
    code = "INVALID_PROMPT"
    status_code = 422
    retryable = False


class VideoProviderError(AppError):
    code = "VIDEO_PROVIDER_ERROR"
    status_code = 502
    retryable = True


class VoiceProviderError(AppError):
    code = "VOICE_PROVIDER_ERROR"
    status_code = 502
    retryable = True


class MusicProviderError(AppError):
    code = "MUSIC_PROVIDER_ERROR"
    status_code = 502
    retryable = True


class RenderError(AppError):
    code = "RENDER_ERROR"
    status_code = 500
    retryable = True


class StorageError(AppError):
    code = "STORAGE_ERROR"
    status_code = 500
    retryable = True


class FileValidationError(AppError):
    code = "FILE_VALIDATION_ERROR"
    status_code = 422
    retryable = False


class ConflictError(AppError):
    code = "CONFLICT"
    status_code = 409
    retryable = False
