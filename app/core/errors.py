import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from sqlalchemy.exc import OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_request_id
from app.security.ratelimit import rate_limit_exceeded_handler

logger = logging.getLogger("app.core.errors")


class AppError(Exception):
    """Base application exception with error code, human-readable message, and HTTP status."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class NotFoundError(AppError):
    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(code="NOT_FOUND", message=message, status_code=404)


class UnauthenticatedError(AppError):
    def __init__(
        self,
        message: str = "Missing or invalid authentication token",
        code: str = "UNAUTHENTICATED",
    ) -> None:
        super().__init__(code=code, message=message, status_code=401)


class ConflictError(AppError):
    def __init__(self, code: str = "ALREADY_MEMBER", message: str = "Resource conflict") -> None:
        super().__init__(code=code, message=message, status_code=409)


class ValidationError(AppError):
    def __init__(self, message: str = "Validation failed", code: str = "VALIDATION_ERROR") -> None:
        super().__init__(code=code, message=message, status_code=422)


class PayerNotMemberError(AppError):
    def __init__(self, message: str = "Payer is not a member of the group") -> None:
        super().__init__(code="PAYER_NOT_MEMBER", message=message, status_code=422)


class ParticipantNotMemberError(AppError):
    def __init__(self, message: str = "Participant is not a member of the group") -> None:
        super().__init__(code="PARTICIPANT_NOT_MEMBER", message=message, status_code=422)


class IdempotencyKeyReusedError(AppError):
    def __init__(
        self, message: str = "Idempotency key reused with different request payload"
    ) -> None:
        super().__init__(code="IDEMPOTENCY_KEY_REUSED", message=message, status_code=422)


class OverpaymentError(AppError):
    def __init__(self, message: str = "Settlement amount exceeds current pairwise debt") -> None:
        super().__init__(code="OVERPAYMENT", message=message, status_code=422)


class InvalidSignatureError(AppError):
    def __init__(self, message: str = "Invalid or missing webhook signature") -> None:
        super().__init__(code="INVALID_SIGNATURE", message=message, status_code=401)


class UnknownKeyIdError(AppError):
    def __init__(self, message: str = "Unknown webhook key identifier") -> None:
        super().__init__(code="UNKNOWN_KEY_ID", message=message, status_code=401)


class StaleTimestampError(AppError):
    def __init__(self, message: str = "Webhook timestamp is outside tolerance window") -> None:
        super().__init__(code="STALE_TIMESTAMP", message=message, status_code=401)


class InvalidTransitionError(AppError):
    def __init__(self, message: str = "Illegal settlement state transition") -> None:
        super().__init__(code="INVALID_TRANSITION", message=message, status_code=422)


class PayloadTooLargeError(AppError):
    def __init__(
        self, message: str = "Request payload exceeds maximum allowed size of 64 KB"
    ) -> None:
        super().__init__(code="PAYLOAD_TOO_LARGE", message=message, status_code=413)


class UnsupportedMediaTypeError(AppError):
    def __init__(
        self, message: str = "Unsupported Media Type: Content-Type must be 'application/json'"
    ) -> None:
        super().__init__(code="UNSUPPORTED_MEDIA_TYPE", message=message, status_code=415)


class RateLimitExceededError(AppError):
    def __init__(self, message: str = "Too many requests. Please retry later.") -> None:
        super().__init__(code="RATE_LIMITED", message=message, status_code=429)


def _resolve_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", None) or get_request_id() or "unknown"


def _error_response(status_code: int, code: str, message: str, request_id: str) -> JSONResponse:
    content: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id,
        }
    }
    return JSONResponse(
        status_code=status_code,
        content=content,
        headers={"X-Request-ID": request_id},
    )


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    request_id = _resolve_request_id(request)
    logger.warning("Application error: %s: %s (request_id=%s)", exc.code, exc.message, request_id)
    return _error_response(
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
        request_id=request_id,
    )


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    request_id = _resolve_request_id(request)
    logger.warning(
        "Validation error on %s %s: %s (request_id=%s)",
        request.method,
        request.url.path,
        exc.errors(),
        request_id,
    )
    return _error_response(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        code="VALIDATION_ERROR",
        message="Invalid request payload or parameters",
        request_id=request_id,
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    request_id = _resolve_request_id(request)
    code = "HTTP_ERROR"
    if exc.status_code == status.HTTP_404_NOT_FOUND:
        code = "NOT_FOUND"
    elif exc.status_code == status.HTTP_405_METHOD_NOT_ALLOWED:
        code = "METHOD_NOT_ALLOWED"
    elif exc.status_code == status.HTTP_403_FORBIDDEN:
        code = "FORBIDDEN"
    elif exc.status_code == status.HTTP_401_UNAUTHORIZED:
        code = "UNAUTHORIZED"
    elif exc.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE:
        code = "PAYLOAD_TOO_LARGE"
    elif exc.status_code == status.HTTP_415_UNSUPPORTED_MEDIA_TYPE:
        code = "UNSUPPORTED_MEDIA_TYPE"
    elif exc.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
        code = "RATE_LIMITED"

    headers = {"X-Request-ID": request_id}
    if exc.headers:
        headers.update(exc.headers)

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": code,
                "message": str(exc.detail),
                "request_id": request_id,
            }
        },
        headers=headers,
    )


async def db_error_handler(request: Request, exc: OperationalError) -> JSONResponse:
    request_id = _resolve_request_id(request)
    logger.error("Database operational error: %s (request_id=%s)", exc, request_id)
    return _error_response(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        code="DATABASE_UNAVAILABLE",
        message="Database connection failed or timed out",
        request_id=request_id,
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = _resolve_request_id(request)
    logger.exception("Unhandled server exception: %s (request_id=%s)", exc, request_id)
    return _error_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        code="INTERNAL_SERVER_ERROR",
        message="An internal server error occurred",
        request_id=request_id,
    )


def register_error_handlers(app: FastAPI) -> None:
    """Register all global error handlers onto the FastAPI application."""
    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(OperationalError, db_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)
