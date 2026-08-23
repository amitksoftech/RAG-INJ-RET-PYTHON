"""Public error types that map cleanly to API responses."""

from __future__ import annotations


class AppError(Exception):
    status_code = 500
    code = "internal_error"

    def __init__(self, message: str, *, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ValidationError(AppError):
    status_code = 422
    code = "validation_error"


class UnsupportedDocumentError(AppError):
    status_code = 415
    code = "unsupported_document"


class PayloadTooLargeError(AppError):
    status_code = 413
    code = "payload_too_large"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class NotConfiguredError(AppError):
    status_code = 503
    code = "provider_not_configured"


class DependencyUnavailableError(AppError):
    status_code = 503
    code = "dependency_unavailable"


class ProviderError(AppError):
    status_code = 502
    code = "provider_error"
