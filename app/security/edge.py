"""Edge hardening middleware: body size limits, Content-Type verification, and security headers."""

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings
from app.core.logging import get_request_id


class EdgeHardeningMiddleware(BaseHTTPMiddleware):
    """Enforce maximum body size cap (64 KB) and JSON content type requirement
    (OWASP API4 / API8).
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = getattr(request.state, "request_id", None) or get_request_id() or "unknown"
        kb_limit = settings.MAX_REQUEST_BODY_BYTES // 1024

        # 1. Fast Content-Length header check
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > settings.MAX_REQUEST_BODY_BYTES:
                    size_msg = f"Request payload exceeds maximum allowed size of {kb_limit} KB"
                    return JSONResponse(
                        status_code=413,
                        content={
                            "error": {
                                "code": "PAYLOAD_TOO_LARGE",
                                "message": size_msg,
                                "request_id": request_id,
                            }
                        },
                        headers={"X-Request-ID": request_id},
                    )
            except ValueError:
                pass

        # 2. Check streamed / chunked body size for write requests
        if request.method in ("POST", "PUT", "PATCH"):
            body = await request.body()
            if len(body) > settings.MAX_REQUEST_BODY_BYTES:
                size_msg = f"Request payload exceeds maximum allowed size of {kb_limit} KB"
                return JSONResponse(
                    status_code=413,
                    content={
                        "error": {
                            "code": "PAYLOAD_TOO_LARGE",
                            "message": size_msg,
                            "request_id": request_id,
                        }
                    },
                    headers={"X-Request-ID": request_id},
                )

            # 3. Content-Type check (reject non-JSON content types with 415)
            if len(body) > 0:
                content_type = request.headers.get("content-type", "")
                if not content_type.lower().startswith("application/json"):
                    media_msg = "Unsupported Media Type: Content-Type must be 'application/json'"
                    return JSONResponse(
                        status_code=415,
                        content={
                            "error": {
                                "code": "UNSUPPORTED_MEDIA_TYPE",
                                "message": media_msg,
                                "request_id": request_id,
                            }
                        },
                        headers={"X-Request-ID": request_id},
                    )

        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Inject defensive HTTP security headers on all responses (OWASP REST Security / API8)."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)

        # Baseline security headers on every response
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = "frame-ancestors 'none'"
        response.headers["Referrer-Policy"] = "no-referrer"

        # HSTS only in production environment (GUARDRAILS E, RFC 6797)
        if settings.APP_ENV == "prod":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        return response
