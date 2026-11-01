"""Public demo deployment gate middleware and access verification."""

import base64
import hmac
from typing import Final

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from app.core.config import settings
from app.core.logging import get_request_id

DEMO_GATE_PATH: Final[str] = "/docs/gate"

HTML_GATE_TEMPLATE: Final[str] = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Akira API — Demo Access Gate</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: #0f172a;
      color: #e2e8f0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 1.5rem;
    }}
    .card {{
      background: #1e293b;
      border: 1px solid #334155;
      border-radius: 12px;
      max-width: 440px;
      width: 100%;
      padding: 2.25rem;
      box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5), 0 8px 10px -6px rgba(0, 0, 0, 0.5);
    }}
    .brand {{
      display: flex;
      align-items: center;
      gap: 0.75rem;
      margin-bottom: 1.25rem;
    }}
    .brand-title {{
      font-size: 1.35rem;
      font-weight: 700;
      letter-spacing: 0.05em;
      color: #f8fafc;
      text-transform: uppercase;
    }}
    .subtitle {{
      color: #94a3b8;
      font-size: 0.9rem;
      line-height: 1.45;
      margin-bottom: 1.75rem;
    }}
    .error-banner {{
      background: rgba(239, 68, 68, 0.15);
      border: 1px solid #ef4444;
      color: #fca5a5;
      padding: 0.75rem 1rem;
      border-radius: 6px;
      font-size: 0.85rem;
      margin-bottom: 1.25rem;
    }}
    label {{
      display: block;
      font-size: 0.825rem;
      font-weight: 600;
      color: #cbd5e1;
      margin-bottom: 0.5rem;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }}
    input[type="password"], input[type="text"] {{
      width: 100%;
      padding: 0.75rem 1rem;
      background: #0f172a;
      border: 1px solid #475569;
      border-radius: 6px;
      color: #f8fafc;
      font-size: 0.95rem;
      margin-bottom: 1.25rem;
      outline: none;
      transition: border-color 0.15s ease;
    }}
    input[type="password"]:focus, input[type="text"]:focus {{
      border-color: #38bdf8;
    }}
    button {{
      width: 100%;
      padding: 0.8rem 1rem;
      background: #0284c7;
      border: none;
      border-radius: 6px;
      color: #ffffff;
      font-size: 0.95rem;
      font-weight: 600;
      cursor: pointer;
      transition: background 0.15s ease;
    }}
    button:hover {{
      background: #0369a1;
    }}
    .hint {{
      margin-top: 1.5rem;
      font-size: 0.775rem;
      color: #64748b;
      line-height: 1.4;
      border-top: 1px solid #334155;
      padding-top: 1rem;
    }}
  </style>
</head>
<body>
  <div class="card">
    <div class="brand">
      <span class="brand-title">Akira</span>
    </div>
    <p class="subtitle">
      This public demo is access-gated to prevent automated crawlers and resource abuse.
      Enter the submission access key to unlock interactive API documentation.
    </p>
    {error_html}
    <form method="POST" action="/docs/gate">
      <label for="demo_key">Demo Access Key</label>
      <input type="password" id="demo_key" name="demo_key"
             placeholder="Enter key..." autofocus required>
      <button type="submit">Unlock Swagger Docs</button>
    </form>
    <div class="hint">
      <strong>For programmatic access / API calls:</strong> Provide the
      <code>X-Demo-Key</code> HTTP header or enter it into Swagger UI's
      <strong>Authorize</strong> modal.
    </div>
  </div>
</body>
</html>
"""


def _render_gate_html(error_message: str | None = None) -> str:
    """Render the minimal self-contained HTML gate page."""
    error_html = f'<div class="error-banner">{error_message}</div>' if error_message else ""
    return HTML_GATE_TEMPLATE.format(error_html=error_html)


def is_demo_access_authorized(request: Request) -> bool:
    """Verify demo access key using constant-time comparison across supported auth vectors:
    1. Header `X-Demo-Key` (primary for API calls, Postman, curl, Swagger UI Authorize).
    2. Cookie `demo_access_key` (browser navigation across /docs, /redoc, /openapi.json).
    3. HTTP Basic Auth `Authorization: Basic ...` (standard browser/HTTP basic auth fallback).
    """
    expected_key = settings.DEMO_ACCESS_KEY.strip()
    if not expected_key:
        return False

    expected_bytes = expected_key.encode("utf-8")

    # 1. Header X-Demo-Key
    header_val = request.headers.get("x-demo-key", "").strip()
    if header_val and hmac.compare_digest(header_val.encode("utf-8"), expected_bytes):
        return True

    # 2. Cookie demo_access_key
    cookie_val = request.cookies.get("demo_access_key", "").strip()
    if cookie_val and hmac.compare_digest(cookie_val.encode("utf-8"), expected_bytes):
        return True

    # 3. HTTP Basic Auth (password == DEMO_ACCESS_KEY)
    auth_val = request.headers.get("authorization", "").strip()
    if auth_val.startswith("Basic "):
        try:
            b64_str = auth_val[6:].strip()
            decoded = base64.b64decode(b64_str).decode("utf-8", errors="ignore")
            _username, _, password = decoded.partition(":")
            if password and hmac.compare_digest(password.encode("utf-8"), expected_bytes):
                return True
        except (ValueError, UnicodeDecodeError):
            pass

    return False


class DemoGateMiddleware(BaseHTTPMiddleware):
    """Enforce DEMO_ACCESS_KEY across all endpoints when APP_ENV=demo (OWASP API1 / API9).

    Exemptions:
    - GET /health: Kept open for Render edge health checks.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if settings.APP_ENV != "demo":
            return await call_next(request)

        # GET /health is strictly exempt to satisfy Render edge health monitoring
        if request.url.path == "/health" and request.method == "GET":
            return await call_next(request)

        request_id = getattr(request.state, "request_id", None) or get_request_id() or "unknown"

        # Handle form submission to /docs/gate
        if request.url.path == DEMO_GATE_PATH and request.method == "POST":
            # Extract key from form data or JSON
            content_type = request.headers.get("content-type", "")
            submitted_key = ""
            if "application/json" in content_type:
                try:
                    data = await request.json()
                    submitted_key = str(data.get("demo_key", "")).strip()
                except Exception:
                    submitted_key = ""
            else:
                form = await request.form()
                submitted_key = str(form.get("demo_key", "")).strip()

            expected_key = settings.DEMO_ACCESS_KEY.strip()
            if submitted_key and hmac.compare_digest(
                submitted_key.encode("utf-8"), expected_key.encode("utf-8")
            ):
                response = RedirectResponse(url="/docs", status_code=303)
                response.set_cookie(
                    key="demo_access_key",
                    value=expected_key,
                    httponly=True,
                    samesite="lax",
                    secure=True,
                    max_age=86400,
                    path="/",
                )
                return response
            else:
                return HTMLResponse(
                    content=_render_gate_html("Invalid access key. Please verify and try again."),
                    status_code=401,
                )

        # Check authorization
        if is_demo_access_authorized(request):
            return await call_next(request)

        # Handle browser navigation to documentation routes
        accept = request.headers.get("accept", "")
        if (
            request.method == "GET"
            and request.url.path in ("/docs", "/redoc")
            and "text/html" in accept
        ):
            return HTMLResponse(
                content=_render_gate_html(),
                status_code=401,
                headers={
                    "WWW-Authenticate": ('Basic realm="Akira Demo - Enter Demo Key as Password"')
                },
            )

        # Standard 401 JSON envelope for all API endpoints and non-browser requests
        return JSONResponse(
            status_code=401,
            content={
                "error": {
                    "code": "UNAUTHORIZED",
                    "message": (
                        "Demo access key required. Provide the 'X-Demo-Key' HTTP header "
                        "or enter it into Swagger UI Authorize dialog."
                    ),
                    "request_id": request_id,
                }
            },
            headers={
                "X-Request-ID": request_id,
                "WWW-Authenticate": 'Basic realm="Akira Demo - Enter Demo Key as Password"',
            },
        )
