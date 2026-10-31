"""Rate limiting configuration and key generators using slowapi (OWASP API4)."""

import hashlib
import logging

from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings
from app.core.logging import get_request_id

proxy_logger = logging.getLogger("app.security.proxy")
_logged_proxy_headers: bool = False


def get_client_ip(request: Request) -> str:
    """Extract client IP behind a reverse proxy (e.g., Render) without spoofing vulnerability.

    Security & Trust Model:
    1. Spoofing Prevention: The leftmost entry in `X-Forwarded-For` is client-controlled and
       untrusted. Malicious clients can prepend arbitrary IPs to bypass rate limits.
    2. Trusted Proxy Walking: We walk `X-Forwarded-For` from the RIGHT, skipping
       `TRUSTED_PROXY_HOPS` entries. By default, `TRUSTED_PROXY_HOPS` is 1 in `demo`/`prod`
       (Render's edge proxy is 1 hop) and 0 in `dev`/`test` (direct connection).
    3. Fallback: If `TRUSTED_PROXY_HOPS <= 0`, or if the header is missing or contains fewer
       entries than `TRUSTED_PROXY_HOPS`, we fall back directly to `request.client.host`.
    4. One-time Startup Debug: In `demo` environment, logs the incoming forwarding headers once
       so the operator can verify Render's proxy behavior in deployment logs without leaking PII.
    """
    global _logged_proxy_headers

    hops = (
        settings.TRUSTED_PROXY_HOPS
        if settings.TRUSTED_PROXY_HOPS is not None
        else (1 if settings.APP_ENV in ("demo", "prod") else 0)
    )

    client_ip: str | None = None

    if hops > 0:
        xff = request.headers.get("X-Forwarded-For")
        if xff:
            ips = [p.strip() for p in xff.split(",") if p.strip()]
            if len(ips) >= hops:
                client_ip = ips[-hops]

    if not client_ip:
        if request.client and request.client.host:
            client_ip = request.client.host
        else:
            client_ip = "127.0.0.1"

    # One-time debug log in demo environment to confirm reverse proxy header behavior
    if settings.APP_ENV == "demo" and not _logged_proxy_headers:
        _logged_proxy_headers = True
        proxy_logger.info(
            "Proxy headers (demo debug): xff=%r, host=%r, ip=%r, hops=%d",
            request.headers.get("X-Forwarded-For"),
            request.client.host if request.client else None,
            client_ip,
            hops,
        )

    return client_ip


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
