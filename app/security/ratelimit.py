"""Rate limiting configuration and key generators using slowapi (OWASP API4)."""

import hashlib

from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings
from app.core.logging import get_request_id


def get_token_or_ip(request: Request) -> str:
    """Return hashed token if authenticated; otherwise fallback to client IP."""
    auth = request.headers.get("Authorization")
    if auth and auth.startswith("Bearer "):
        token = auth[7:].strip()
        if token:
            return f"token:{hashlib.sha256(token.encode('utf-8')).hexdigest()}"
    return f"ip:{get_remote_address(request)}"


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
