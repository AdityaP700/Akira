"""Tests for APP_ENV profiles: demo vs prod (GUARDRAILS P9 / D1 Part 3 Item 2)."""

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import create_app


def test_demo_profile_hardened_with_docs_mock_provider_and_header():
    """Verify APP_ENV=demo retains prod hardening, enables /docs & /dev routes,

    and emits X-Environment: demo-mock-payments.
    """
    orig_env = settings.APP_ENV
    try:
        settings.APP_ENV = "demo"
        demo_app = create_app()
        client = TestClient(demo_app)

        # 1. Interactive documentation MUST be enabled in demo
        docs_res = client.get("/docs")
        assert docs_res.status_code == 200

        openapi_res = client.get("/openapi.json")
        assert openapi_res.status_code == 200
        assert openapi_res.headers.get("content-type") == "application/json"

        # 2. Mock payment simulation routes MUST be mounted in demo (route exists)
        dev_res = client.post("/dev/mock-provider/pay/stl_nonexistent")
        # Route is mounted; handler executes and returns app-level NOT_FOUND
        assert dev_res.status_code == 404
        assert dev_res.json()["error"]["code"] == "NOT_FOUND"

        # 3. Defensive security headers + X-Environment: demo-mock-payments MUST be present
        health_res = client.get("/health")
        assert health_res.status_code == 200
        assert health_res.headers.get("X-Environment") == "demo-mock-payments"
        assert health_res.headers.get("X-Content-Type-Options") == "nosniff"
        assert health_res.headers.get("Cache-Control") == "no-store"
        assert health_res.headers.get("Content-Security-Policy") == "frame-ancestors 'none'"
    finally:
        settings.APP_ENV = orig_env


def test_prod_profile_disables_docs_mock_provider_and_enforces_hsts():
    """Verify APP_ENV=prod disables /docs, /redoc, /openapi.json, unmounts /dev routes,

    and enforces Strict-Transport-Security without demo header.
    """
    orig_env = settings.APP_ENV
    try:
        settings.APP_ENV = "prod"
        prod_app = create_app()
        client = TestClient(prod_app)

        # 1. Interactive documentation MUST be disabled in prod (OWASP API9 / GUARDRAILS P9)
        docs_res = client.get("/docs")
        assert docs_res.status_code == 404

        redoc_res = client.get("/redoc")
        assert redoc_res.status_code == 404

        openapi_res = client.get("/openapi.json")
        assert openapi_res.status_code == 404

        # 2. Mock payment simulation routes MUST NOT be mounted in prod (unrouted 404)
        dev_res = client.post("/dev/mock-provider/pay/stl_nonexistent")
        assert dev_res.status_code == 404
        assert dev_res.json()["error"]["code"] == "NOT_FOUND"
        assert dev_res.json()["error"]["message"] == "Not Found"

        # 3. Response headers: HSTS enabled, X-Environment NOT set to demo
        health_res = client.get("/health")
        assert health_res.status_code == 200
        assert "Strict-Transport-Security" in health_res.headers
        assert health_res.headers.get("X-Environment") != "demo-mock-payments"
        assert health_res.headers.get("X-Content-Type-Options") == "nosniff"
    finally:
        settings.APP_ENV = orig_env
