"""Comprehensive test suite for Phase A2: Edge Hardening, Abuse Protection, Observability.

Covers:
1. Body size cap 64 KB -> 413 PAYLOAD_TOO_LARGE (Content-Length and streamed body).
2. Content-Type rejection -> 415 UNSUPPORTED_MEDIA_TYPE for non-JSON payloads.
3. Rate limiting -> 429 RATE_LIMITED with Retry-After header and uniform envelope.
4. Defensive security headers on all responses (X-Content-Type-Options,
   Cache-Control, CSP, Referrer-Policy, HSTS in prod).
5. OpenAPI / Swagger documentation disabled when APP_ENV=prod (OWASP API9 Inventory).
6. Structured JSON logging with route template, latency, request_id, and secret/VPA masking.
7. Unhandled exception safety (generic 500 without stack trace leakage).
8. Database timeout / unavailable error (503 DATABASE_UNAVAILABLE).
"""

import io
import json
import logging
from collections.abc import Generator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_db
from app.core.config import settings
from app.core.logging import JSONLogFormatter, MaskingFilter
from app.main import app, create_app
from app.security.ratelimit import limiter


@pytest.fixture
def edge_client(session_factory: sessionmaker) -> Generator[TestClient, None, None]:
    def override_get_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    try:
        yield client
    finally:
        app.dependency_overrides.clear()


# ==============================================================================
# 1. Body Size Limit Tests (413 PAYLOAD_TOO_LARGE)
# ==============================================================================


def test_payload_too_large_content_length_header(edge_client: TestClient) -> None:
    """Requests exceeding 64 KB via Content-Length header are rejected immediately with 413."""
    oversized_length = str(settings.MAX_REQUEST_BODY_BYTES + 1024)
    resp = edge_client.post(
        "/users",
        content=b'{"name": "test"}',
        headers={"Content-Type": "application/json", "Content-Length": oversized_length},
    )
    assert resp.status_code == 413
    data = resp.json()
    assert data["error"]["code"] == "PAYLOAD_TOO_LARGE"
    assert "64 KB" in data["error"]["message"]
    assert "request_id" in data["error"]
    assert "X-Request-ID" in resp.headers


def test_payload_too_large_actual_streamed_body(edge_client: TestClient) -> None:
    """Requests exceeding 64 KB streamed body are rejected with 413 even if no Content-Length."""
    # Create payload larger than 64 KB
    large_payload = json.dumps({"name": "A" * (settings.MAX_REQUEST_BODY_BYTES + 100)})
    resp = edge_client.post(
        "/users",
        content=large_payload,
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 413
    data = resp.json()
    assert data["error"]["code"] == "PAYLOAD_TOO_LARGE"


def test_payload_within_limit_succeeds(edge_client: TestClient) -> None:
    """Requests within the 64 KB limit succeed normally."""
    valid_payload = {"name": "Valid User"}
    resp = edge_client.post(
        "/users",
        json=valid_payload,
    )
    assert resp.status_code == 201


# ==============================================================================
# 2. Content-Type Validation Tests (415 UNSUPPORTED_MEDIA_TYPE)
# ==============================================================================


def test_reject_non_json_content_types(edge_client: TestClient) -> None:
    """Non-JSON Content-Type on write endpoints is rejected with 415."""
    for bad_type in ("text/plain", "application/xml", "application/x-www-form-urlencoded"):
        resp = edge_client.post(
            "/users",
            content=b"<user><name>Test</name></user>",
            headers={"Content-Type": bad_type},
        )
        assert resp.status_code == 415
        data = resp.json()
        assert data["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"
        assert "Content-Type must be 'application/json'" in data["error"]["message"]
        assert "request_id" in data["error"]


def test_accept_json_content_types(edge_client: TestClient) -> None:
    """Valid JSON content types (including charset parameter) are accepted."""
    resp = edge_client.post(
        "/users",
        content=b'{"name": "Charset Test"}',
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    assert resp.status_code == 201


# ==============================================================================
# 3. Rate Limiting Tests (429 RATE_LIMITED & Retry-After)
# ==============================================================================


def test_rate_limiting_enforcement_and_retry_after(edge_client: TestClient) -> None:
    """Exceeding rate limit returns 429 RATE_LIMITED with Retry-After header."""
    limiter.enabled = True
    limiter.reset()

    try:
        # POST /users limit is 5 per minute in default settings
        responses = []
        for i in range(7):
            res = edge_client.post("/users", json={"name": f"RateUser{i}"})
            responses.append(res)

        status_codes = [r.status_code for r in responses]
        assert 429 in status_codes

        rate_limited_res = next(r for r in responses if r.status_code == 429)
        assert rate_limited_res.status_code == 429
        data = rate_limited_res.json()
        assert data["error"]["code"] == "RATE_LIMITED"
        assert "Rate limit exceeded" in data["error"]["message"]
        assert "request_id" in data["error"]
        assert "Retry-After" in rate_limited_res.headers
        assert int(rate_limited_res.headers["Retry-After"]) >= 1
    finally:
        limiter.reset()
        limiter.enabled = False


# ==============================================================================
# 4. Security Headers Tests
# ==============================================================================


def test_security_headers_present_on_all_responses(edge_client: TestClient) -> None:
    """Defensive security headers are injected on success and error responses."""
    # Test 200 OK
    resp_ok = edge_client.get("/health")
    assert resp_ok.headers["X-Content-Type-Options"] == "nosniff"
    assert resp_ok.headers["Cache-Control"] == "no-store"
    assert resp_ok.headers["Content-Security-Policy"] == "frame-ancestors 'none'"
    assert resp_ok.headers["Referrer-Policy"] == "no-referrer"
    assert "Strict-Transport-Security" not in resp_ok.headers  # absent in dev

    # Test 404 Error response
    resp_err = edge_client.get("/non-existent-endpoint")
    assert resp_err.headers["X-Content-Type-Options"] == "nosniff"
    assert resp_err.headers["Cache-Control"] == "no-store"
    assert resp_err.headers["Content-Security-Policy"] == "frame-ancestors 'none'"
    assert resp_err.headers["Referrer-Policy"] == "no-referrer"


def test_hsts_header_present_in_prod_mode() -> None:
    """Strict-Transport-Security is enabled only when APP_ENV is prod."""
    with patch.object(settings, "APP_ENV", "prod"):
        prod_app = create_app()
        prod_client = TestClient(prod_app)
        resp = prod_client.get("/health")
        assert "Strict-Transport-Security" in resp.headers
        assert "max-age=31536000" in resp.headers["Strict-Transport-Security"]


# ==============================================================================
# 5. Inventory & Swagger Disabled in Prod Mode (OWASP API9)
# ==============================================================================


def test_api_docs_accessible_in_dev_mode(edge_client: TestClient) -> None:
    """Interactive documentation endpoints are accessible in dev/test environment."""
    assert edge_client.get("/docs").status_code == 200
    assert edge_client.get("/openapi.json").status_code == 200


def test_api_docs_disabled_in_prod_mode() -> None:
    """Interactive documentation (/docs, /redoc, /openapi.json) is disabled in production."""
    with patch.object(settings, "APP_ENV", "prod"):
        prod_app = create_app()
        prod_client = TestClient(prod_app)
        assert prod_client.get("/docs").status_code == 404
        assert prod_client.get("/redoc").status_code == 404
        assert prod_client.get("/openapi.json").status_code == 404


# ==============================================================================
# 6. Structured JSON Logging & Masking Tests
# ==============================================================================


def test_log_masking_filter_and_formatter() -> None:
    """Logging filter and formatter mask sensitive tokens, VPAs, phones, and signatures."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JSONLogFormatter())
    handler.addFilter(MaskingFilter())

    test_logger = logging.getLogger("test.security")
    test_logger.setLevel(logging.INFO)
    test_logger.handlers = [handler]
    test_logger.propagate = False

    sample_val = f"est_{'x' * 32}"
    raw_vpa = "mohit.sharma@okaxis"
    raw_phone = "+919876543210"
    raw_sig = "v1=0123456789abcdef0123456789abcdef"

    test_logger.info(
        "Sensitive event with token=%s, vpa=%s, phone=%s, sig=%s",
        sample_val,
        raw_vpa,
        raw_phone,
        raw_sig,
    )

    log_output = stream.getvalue()
    log_data = json.loads(log_output.strip())

    # Assert raw sensitive data NEVER appears in output
    assert sample_val not in log_output
    assert raw_vpa not in log_output
    assert raw_phone not in log_output
    assert raw_sig not in log_output

    # Assert masked variants appear
    assert "est_***" in log_data["message"]
    assert "mo***@okaxis" in log_data["message"]
    assert "987****210" in log_data["message"]
    assert "v1=***" in log_data["message"]


def test_direct_masking_helpers() -> None:
    """Direct unit tests for masking utilities."""
    from app.security.masking import mask_phone, mask_sensitive_text, mask_token, mask_vpa

    assert mask_token("est_1234567890") == "est_***"
    assert mask_token("other_token") == "***"
    assert mask_vpa("mohit@okaxis") == "mo***@okaxis"
    assert mask_vpa("a@okaxis") == "a***@okaxis"
    assert mask_vpa("no_at_sign") == "***"
    assert mask_phone("+919876543210") == "+91987****210"
    assert mask_sensitive_text("") == ""


def test_access_log_contains_route_template_not_raw_ids(edge_client: TestClient) -> None:
    """HTTP access logs record parameterized route templates and latency instead of raw IDs."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JSONLogFormatter())

    access_logger = logging.getLogger("app.access")
    access_logger.handlers = [handler]
    access_logger.propagate = False

    resp = edge_client.get("/health")
    assert resp.status_code == 200

    log_output = stream.getvalue()
    assert log_output != ""
    log_data = json.loads(log_output.strip().split("\n")[-1])
    assert log_data["method"] == "GET"
    assert log_data["route_template"] == "/health"
    assert log_data["status"] == 200
    assert "latency_ms" in log_data
    assert "request_id" in log_data


# ==============================================================================
# 7. Unhandled Exception & DB Timeout Safety
# ==============================================================================


def test_unhandled_exception_returns_generic_500_without_stack_trace(
    edge_client: TestClient,
) -> None:
    """Unhandled server errors return generic 500 without leaking stack traces."""
    safe_client = TestClient(app, raise_server_exceptions=False)
    with patch(
        "app.services.users.create_user",
        side_effect=RuntimeError("Secret database crash details!"),
    ):
        resp = safe_client.post("/users", json={"name": "Crash User"})
        assert resp.status_code == 500
        data = resp.json()
        assert data["error"]["code"] == "INTERNAL_SERVER_ERROR"
        assert data["error"]["message"] == "An internal server error occurred"
        assert "Secret database crash details!" not in resp.text
        assert "Traceback" not in resp.text
        assert "request_id" in data["error"]


def test_db_timeout_returns_503_database_unavailable(edge_client: TestClient) -> None:
    """Database connectivity failure or timeout returns 503 DATABASE_UNAVAILABLE."""
    with patch(
        "app.services.users.create_user",
        side_effect=OperationalError("connection timeout expired", params={}, orig=Exception()),
    ):
        resp = edge_client.post("/users", json={"name": "DB Timeout User"})
        assert resp.status_code == 503
        data = resp.json()
        assert data["error"]["code"] == "DATABASE_UNAVAILABLE"
        assert "Database connection failed or timed out" in data["error"]["message"]
        assert "request_id" in data["error"]


def test_forwarded_client_ip_spoofing_defense() -> None:
    """Verify get_client_ip walks from the right skipping TRUSTED_PROXY_HOPS,

    ensuring client-spoofed leftmost entries cannot bypass rate limits.
    """
    from starlette.datastructures import Headers

    from app.security.ratelimit import get_client_ip

    class DummyClient:
        host = "10.0.0.2"

    class DummyRequest:
        def __init__(self, headers: dict[str, str], client_host: str = "10.0.0.2"):
            self.headers = Headers(headers)
            self.client = DummyClient()
            self.client.host = client_host

    orig_hops = settings.TRUSTED_PROXY_HOPS
    try:
        # With 1 trusted proxy hop (e.g. Render edge):
        settings.TRUSTED_PROXY_HOPS = 1

        # 1. Attacker prepends fake IP "1.1.1.1"; proxy appends real IP "203.0.113.50"
        req_spoofed = DummyRequest({"X-Forwarded-For": "1.1.1.1, 203.0.113.50"})
        # Leftmost "1.1.1.1" MUST be ignored; real IP "203.0.113.50" MUST be returned
        assert get_client_ip(req_spoofed) == "203.0.113.50"

        # 2. Multi-hop proxy chain: client prepends "attacker.fake", real client is "198.51.100.42",
        # followed by internal proxy "10.0.0.1". With hops=2, index is -2.
        settings.TRUSTED_PROXY_HOPS = 2
        req_multi = DummyRequest({"X-Forwarded-For": "attacker.fake, 198.51.100.42, 10.0.0.1"})
        assert get_client_ip(req_multi) == "198.51.100.42"

        # 3. Fewer entries than hops falls back to request.client.host
        settings.TRUSTED_PROXY_HOPS = 3
        req_short = DummyRequest({"X-Forwarded-For": "198.51.100.42"}, client_host="10.0.0.9")
        assert get_client_ip(req_short) == "10.0.0.9"

        # 4. Missing header falls back to request.client.host
        req_missing = DummyRequest({}, client_host="10.0.0.9")
        assert get_client_ip(req_missing) == "10.0.0.9"
    finally:
        settings.TRUSTED_PROXY_HOPS = orig_hops


def test_hops_zero_ignores_x_forwarded_for_entirely() -> None:
    """When TRUSTED_PROXY_HOPS=0 (dev/test), X-Forwarded-For is ignored completely."""
    from starlette.datastructures import Headers

    from app.security.ratelimit import get_client_ip

    class DummyClient:
        host = "127.0.0.1"

    class DummyRequest:
        def __init__(self, headers: dict[str, str], client_host: str = "127.0.0.1"):
            self.headers = Headers(headers)
            self.client = DummyClient()
            self.client.host = client_host

    orig_hops = settings.TRUSTED_PROXY_HOPS
    try:
        settings.TRUSTED_PROXY_HOPS = 0
        req = DummyRequest(
            {"X-Forwarded-For": "203.0.113.195, 10.0.0.1"}, client_host="192.168.1.5"
        )
        # Ignores header and uses client.host
        assert get_client_ip(req) == "192.168.1.5"
    finally:
        settings.TRUSTED_PROXY_HOPS = orig_hops


def test_two_clients_with_different_real_ips_are_limited_separately(
    edge_client: TestClient,
) -> None:
    """Two clients with identical spoofed leftmost headers but different real IPs

    are tracked in distinct rate limiting buckets.
    """
    orig_hops = settings.TRUSTED_PROXY_HOPS
    orig_enabled = limiter.enabled
    try:
        settings.TRUSTED_PROXY_HOPS = 1
        limiter.enabled = True

        # Client A: spoofed 1.1.1.1, real 203.0.113.10
        # Client B: spoofed 1.1.1.1, real 203.0.113.20
        headers_a = {"X-Forwarded-For": "1.1.1.1, 203.0.113.10"}
        headers_b = {"X-Forwarded-For": "1.1.1.1, 203.0.113.20"}

        # Client A consumes registration quota (limit is 5/minute)
        for _ in range(5):
            res_a = edge_client.post("/users", json={"name": "User A"}, headers=headers_a)
            assert res_a.status_code == 201

        # 6th request from Client A is rate limited
        blocked_a = edge_client.post("/users", json={"name": "User A Exceeded"}, headers=headers_a)
        assert blocked_a.status_code == 429

        # Client B has separate real IP so its quota is NOT exhausted
        res_b = edge_client.post("/users", json={"name": "User B"}, headers=headers_b)
        assert res_b.status_code == 201
    finally:
        settings.TRUSTED_PROXY_HOPS = orig_hops
        limiter.enabled = orig_enabled
