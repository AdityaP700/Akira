import json
import logging
import re
import sys
import time
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.security.masking import mask_sensitive_text

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")
SAFE_REQUEST_ID_REGEX = re.compile(r"^[a-zA-Z0-9_\-]{8,64}$")
access_logger = logging.getLogger("app.access")


def get_request_id() -> str:
    """Return the current request_id from context."""
    return request_id_ctx.get()


class MaskingFilter(logging.Filter):
    """Filter that sanitizes log records to ensure no tokens, VPAs, or phones leak."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = mask_sensitive_text(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: mask_sensitive_text(str(v)) if isinstance(v, str) else v
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    mask_sensitive_text(str(v)) if isinstance(v, str) else v for v in record.args
                )
        return True


class JSONLogFormatter(logging.Formatter):
    """Outputs structured JSON logs with timestamp, level, message, logger, and request_id."""

    def format(self, record: logging.LogRecord) -> str:
        msg = mask_sensitive_text(record.getMessage())
        log_obj: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "message": msg,
            "logger": record.name,
            "request_id": getattr(record, "request_id", None) or get_request_id() or None,
        }
        for attr in ("method", "route_template", "status", "latency_ms", "actor_public_id"):
            val = getattr(record, attr, None)
            if val is not None:
                log_obj[attr] = val

        if record.exc_info:
            log_obj["exception"] = mask_sensitive_text(self.formatException(record.exc_info))
        return json.dumps(log_obj)


def setup_logging(level: int = logging.INFO) -> None:
    """Configure root logger to output structured JSON with masking filter."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONLogFormatter())
    handler.addFilter(MaskingFilter())
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers = [handler]


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware that sets X-Request-ID and logs HTTP access with latency, status, and route."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming_id = request.headers.get("X-Request-ID")
        if incoming_id and SAFE_REQUEST_ID_REGEX.match(incoming_id):
            request_id = incoming_id
        else:
            request_id = f"req_{uuid.uuid4().hex[:16]}"

        request.state.request_id = request_id
        token = request_id_ctx.set(request_id)
        start_time = time.perf_counter()
        status_code = 500

        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            route = request.scope.get("route")
            route_template = route.path if route and hasattr(route, "path") else request.url.path
            actor_id = getattr(request.state, "actor_public_id", None)

            extra: dict[str, Any] = {
                "method": request.method,
                "route_template": route_template,
                "status": status_code,
                "latency_ms": latency_ms,
                "actor_public_id": actor_id,
                "request_id": request_id,
            }
            access_logger.info(
                "%s %s -> %s (%s ms)",
                request.method,
                route_template,
                status_code,
                latency_ms,
                extra=extra,
            )
            request_id_ctx.reset(token)


# Backwards compatibility alias
RequestIDMiddleware = RequestLoggingMiddleware
