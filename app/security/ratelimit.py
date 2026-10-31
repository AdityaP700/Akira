"""Rate limiting configuration and key generators using slowapi (OWASP API4)."""

import hashlib

from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings
from app.core.logging import get_request_id


def get_client_ip(request: Request) -> str:
    """Extract client IP behind Render's reverse proxy.

    Trust Assumption & Security Model:
    1. Reverse Proxy Boundary: Render terminates external TLS at its edge ingress proxy
       and forwards requests to the Docker container over an internal private network.
    2. Header Forwarding: Render sets or appends the client IP in the `X-Forwarded-For`
       header. The leftmost IP represents the original client initiating the request.
    3. Fallback: If `X-Forwarded-For` is absent (direct connection or local testing),
       we fall back to `request.client.host`, and lastly to '127.0.0.1'.
    """
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        client_ip = xff.split(",")[0].strip()
        if client_ip:
            return client_ip
    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"


def get_token_or_ip(request: Request) -> str:
    """Return hashed token if authenticated; otherwise fallback to forwarded client IP."""
    auth = request.headers.get("Authorization")
    if auth and auth.startswith("Bearer "):
        token = auth[7:].strip()
        if token:
            return f"token:{hashlib.sha256(token.encode('utf-8')).hexdigest()}"
    return f"ip:{get_client_ip(request)}"


limiter: Limiter = Limiter(
    key_func=get_token_or_ip,
    default_limits=[settings.RATE_LIMIT_AUTHENTICATED] if settings.RATE_LIMIT_ENABLED else [],
    enabled=settings.RATE_LIMIT_ENABLED,
    headers_enabled=False,
)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> Response:
    """Uniform RFC 6585 rate limit error response with Retry-After header and error envelope."""
    request_id = getattr(request.state, "request_id", None) or get_request_id() or "unknown"
    return JSONResponse(
        status_code=429,
        content={
            "error": {
                "code": "RATE_LIMITED",
                "message": f"Rate limit exceeded: {exc.detail}",
                "request_id": request_id,
            }
        },
        headers={"X-Request-ID": request_id, "Retry-After": "60"},
    )
