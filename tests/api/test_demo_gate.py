"""Tests for public demo deployment gate (DEMO_ACCESS_KEY), Swagger integration, and rate limits."""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_db
from app.core.config import Settings, settings
from app.main import app, create_app
from app.security.ratelimit import limiter


@pytest.fixture
def demo_client(session_factory: sessionmaker) -> Generator[TestClient, None, None]:
    """Provide a TestClient with database overrides and demo settings."""

    def override_get_db() -> Generator[Session, None, None]:
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
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def demo_key(monkeypatch) -> str:
    """Fixture that switches settings to APP_ENV=demo with a test DEMO_ACCESS_KEY."""
    test_key = "test_demo_secret_access_key_999"
    monkeypatch.setattr(settings, "APP_ENV", "demo")
    monkeypatch.setattr(settings, "DEMO_ACCESS_KEY", test_key)
    return test_key


def test_demo_mode_health_check_is_strictly_exempt(demo_client: TestClient, demo_key: str) -> None:
    """Verify GET /health is completely exempt from DEMO_ACCESS_KEY in demo environment."""
    response = demo_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["db"] == "ok"


def test_demo_mode_blocks_unauthorized_api_requests(demo_client: TestClient, demo_key: str) -> None:
    """Verify demo mode rejects missing or invalid X-Demo-Key with 401 and standard error body."""
    # 1. Missing header entirely
    res1 = demo_client.get("/users")
    assert res1.status_code == 401
    body1 = res1.json()
    assert body1["error"]["code"] == "UNAUTHORIZED"
    assert "Demo access key required" in body1["error"]["message"]
    assert "request_id" in body1["error"]
    assert res1.headers.get("X-Request-ID") == body1["error"]["request_id"]

    # 2. Invalid / wrong header
    res2 = demo_client.get("/users", headers={"X-Demo-Key": "wrong_key_attempt"})
    assert res2.status_code == 401
    body2 = res2.json()
    assert body2["error"]["code"] == "UNAUTHORIZED"


def test_demo_mode_allows_requests_with_valid_x_demo_key(
    demo_client: TestClient, demo_key: str
) -> None:
    """Verify demo mode allows requests when valid X-Demo-Key header is provided."""
    response = demo_client.post(
        "/users",
        json={"name": "Demo Gate Tester"},
        headers={"X-Demo-Key": demo_key},
    )
    assert response.status_code == 201
    data = response.json()
    assert "user" in data
    assert data["user"]["name"] == "Demo Gate Tester"
    assert "api_token" in data


def test_demo_mode_openapi_and_docs_gating(demo_client: TestClient, demo_key: str) -> None:
    """Verify /openapi.json and /docs are protected by the demo gate and contain DemoKeyAuth."""
    # 1. /openapi.json without key -> 401
    res_oa_unauth = demo_client.get("/openapi.json")
    assert res_oa_unauth.status_code == 401

    # 2. /openapi.json with key -> 200 with OpenAPI schema
    res_oa_auth = demo_client.get("/openapi.json", headers={"X-Demo-Key": demo_key})
    assert res_oa_auth.status_code == 200
    schema = res_oa_auth.json()
    assert "components" in schema
    assert "securitySchemes" in schema["components"]
    assert "DemoKeyAuth" in schema["components"]["securitySchemes"]
    assert schema["components"]["securitySchemes"]["DemoKeyAuth"]["name"] == "X-Demo-Key"
    assert {"DemoKeyAuth": []} in schema["security"]

    # 3. /docs with non-browser Accept (e.g. application/json or curl) -> 401 JSON
    res_docs_curl = demo_client.get("/docs", headers={"Accept": "application/json"})
    assert res_docs_curl.status_code == 401
    assert res_docs_curl.json()["error"]["code"] == "UNAUTHORIZED"

    # 4. /docs with valid X-Demo-Key -> 200 HTML
    res_docs_auth = demo_client.get("/docs", headers={"X-Demo-Key": demo_key})
    assert res_docs_auth.status_code == 200
    assert "swagger-ui" in res_docs_auth.text.lower()


def test_demo_mode_browser_html_gate_flow(demo_client: TestClient, demo_key: str) -> None:
    """Verify the browser HTML gate renders on browser navigation and unlocks via cookie."""
    # 1. Browser navigation to /docs (Accept: text/html) without key -> 401 HTML gate
    res_browser = demo_client.get("/docs", headers={"Accept": "text/html,application/xhtml+xml"})
    assert res_browser.status_code == 401
    assert "Akira API — Demo Access Gate" in res_browser.text
    assert 'action="/docs/gate"' in res_browser.text

    # 2. Form submission with wrong key -> 401 with error message
    res_fail = demo_client.post(
        "/docs/gate",
        data={"demo_key": "wrong_password"},
        headers={"Accept": "text/html"},
    )
    assert res_fail.status_code == 401
    assert "Invalid access key" in res_fail.text

    # 3. Form submission with correct key -> 303 Redirect with cookie
    res_unlock = demo_client.post(
        "/docs/gate",
        data={"demo_key": demo_key},
        follow_redirects=False,
    )
    assert res_unlock.status_code == 303
    assert res_unlock.headers["location"] == "/docs"
    assert "demo_access_key" in res_unlock.cookies

    # 4. Subsequent requests using the issued cookie unlock docs and openapi.json
    cookie_val = res_unlock.cookies["demo_access_key"]
    res_docs_cookie = demo_client.get("/docs", cookies={"demo_access_key": cookie_val})
    assert res_docs_cookie.status_code == 200

    res_oa_cookie = demo_client.get("/openapi.json", cookies={"demo_access_key": cookie_val})
    assert res_oa_cookie.status_code == 200


def test_demo_mode_basic_auth_fallback(demo_client: TestClient, demo_key: str) -> None:
    """Verify HTTP Basic Auth header can unlock endpoints for HTTP tools/browsers."""
    res = demo_client.get("/docs", auth=("any_user", demo_key))
    assert res.status_code == 200


def test_demo_mode_dev_mock_provider_gated(demo_client: TestClient, demo_key: str) -> None:
    """Verify /dev/mock-provider routes require the demo key in demo mode."""
    # 1. Without demo key -> 401
    res_unauth = demo_client.post("/dev/mock-provider/pay/settlement_nonexistent")
    assert res_unauth.status_code == 401

    # 2. With demo key -> passes demo gate (reaches route handler -> 404 for unknown ref)
    res_auth = demo_client.post(
        "/dev/mock-provider/pay/settlement_nonexistent",
        headers={"X-Demo-Key": demo_key},
    )
    assert res_auth.status_code == 404
    assert res_auth.json()["error"]["code"] == "NOT_FOUND"


def test_prod_mode_disabled_routes_and_no_demo_gate(
    demo_client: TestClient, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker
) -> None:
    """Verify in APP_ENV=prod, regular routes work without demo key and /dev & /docs are 404."""
    monkeypatch.setattr(settings, "APP_ENV", "prod")
    prod_app = create_app()

    def override_get_db() -> Generator[Session, None, None]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    prod_app.dependency_overrides[get_db] = override_get_db
    prod_client = TestClient(prod_app)

    # 1. Regular routes do not require demo key
    res_user = prod_client.post("/users", json={"name": "Prod Mode User"})
    assert res_user.status_code == 201

    # 2. Docs endpoints are 404 in production (GUARDRAILS P9)
    assert prod_client.get("/docs").status_code == 404
    assert prod_client.get("/redoc").status_code == 404
    assert prod_client.get("/openapi.json").status_code == 404

    # 3. Dev mock-provider is disabled (404) in production
    assert prod_client.post("/dev/mock-provider/pay/any_ref").status_code == 404


def test_test_mode_unaffected(demo_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that in APP_ENV=test, normal API routes function with zero demo key requirements."""
    monkeypatch.setattr(settings, "APP_ENV", "test")
    response = demo_client.post("/users", json={"name": "Test Environment User"})
    assert response.status_code == 201
    assert "user" in response.json()


def test_demo_user_registration_global_rate_limit(
    demo_client: TestClient, demo_key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify POST /users global rate limit in demo mode triggers when cap is exceeded."""
    limiter.enabled = True
    limiter.reset()
    try:
        # Lower limit temporarily to 2/hour to verify global cap without 50 roundtrips
        monkeypatch.setattr(settings, "RATE_LIMIT_DEMO_GLOBAL_REGISTRATION", "2/hour")
        # Ensure per-IP limit is loose so only global limit triggers
        monkeypatch.setattr(settings, "RATE_LIMIT_USER_REGISTRATION", "100/minute")

        headers = {"X-Demo-Key": demo_key}
        # First 2 requests succeed
        r1 = demo_client.post("/users", json={"name": "User 1"}, headers=headers)
        assert r1.status_code == 201
        r2 = demo_client.post("/users", json={"name": "User 2"}, headers=headers)
        assert r2.status_code == 201

        # 3rd request from any IP hits global cap -> 429
        r3 = demo_client.post(
            "/users",
            json={"name": "User 3"},
            headers={**headers, "X-Forwarded-For": "198.51.100.1"},
        )
        assert r3.status_code == 429
        assert r3.json()["error"]["code"] == "RATE_LIMITED"
        assert "Retry-After" in r3.headers
    finally:
        limiter.reset()
        limiter.enabled = False


def test_settings_fail_fast_when_demo_access_key_missing() -> None:
    """Verify Settings raises ValueError when DEMO_ACCESS_KEY is empty outside test/alembic."""
    valid_secrets = {
        "DATABASE_URL": "postgresql+psycopg://postgres:secret@localhost:5432/akira_test",
        "WEBHOOK_HMAC_KEY": "11" * 32,
        "WEBHOOK_KEY_ID": "wh_key",
        "AUDIT_HMAC_KEY": "22" * 32,
        "AUDIT_KEY_ID": "audit_key",
        "PII_ENC_KEY": "33" * 32,
        "PII_BLIND_INDEX_KEY": "44" * 32,
        "PII_KEY_ID": "pii_key",
    }

    # In APP_ENV=demo with empty DEMO_ACCESS_KEY -> must fail fast
    with pytest.raises(
        ValueError, match="Missing required security environment variable.*DEMO_ACCESS_KEY"
    ):
        Settings(
            APP_ENV="demo",
            DEMO_ACCESS_KEY="",
            **valid_secrets,
        )

    # In APP_ENV=demo with valid DEMO_ACCESS_KEY -> succeeds
    st = Settings(
        APP_ENV="demo",
        DEMO_ACCESS_KEY="valid_demo_key_123",
        **valid_secrets,
    )
    assert st.DEMO_ACCESS_KEY == "valid_demo_key_123"
    # Never log DEMO_ACCESS_KEY in repr or str
    assert "valid_demo_key_123" not in repr(st)
    assert "valid_demo_key_123" not in str(st)
