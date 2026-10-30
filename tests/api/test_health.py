from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_db
from app.core.errors import AppError
from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_health_ok_path(client: TestClient) -> None:
    """Verify GET /health returns 200 ok when database query succeeds."""
    # PostgreSQL test database connection for the ok path
    from app.core.config import settings

    test_engine = create_engine(settings.TEST_DATABASE_URL)
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    def override_get_db() -> Generator[Session, None, None]:
        session = TestSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data == {"status": "ok", "db": "ok"}
        assert "X-Request-ID" in response.headers
    finally:
        app.dependency_overrides.clear()


def test_health_db_down_path(client: TestClient) -> None:
    """Verify GET /health returns 503 degraded when database connection fails."""
    # Point at an unreachable port with short timeout to simulate database down
    bad_engine = create_engine(
        "postgresql+psycopg://baduser:badpass@127.0.0.1:54329/nonexistent",
        connect_args={"connect_timeout": 1},
    )
    BadSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=bad_engine)

    def override_get_bad_db() -> Generator[Session, None, None]:
        session = BadSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_bad_db
    try:
        response = client.get("/health")
        assert response.status_code == 503
        data = response.json()
        assert data == {"status": "degraded", "db": "down"}
        assert "X-Request-ID" in response.headers
    finally:
        app.dependency_overrides.clear()


def test_request_id_header_propagated(client: TestClient) -> None:
    """Verify incoming X-Request-ID header is accepted and echoed back."""
    from app.core.config import settings

    test_engine = create_engine(settings.TEST_DATABASE_URL)
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    def override_get_db() -> Generator[Session, None, None]:
        session = TestSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        custom_id = "test-req-id-12345"
        response = client.get("/health", headers={"X-Request-ID": custom_id})
        assert response.status_code == 200
        assert response.headers.get("X-Request-ID") == custom_id
    finally:
        app.dependency_overrides.clear()


def test_error_envelope_format_on_404(client: TestClient) -> None:
    """Verify 404 errors return the standard error envelope with request_id."""
    response = client.get("/nonexistent-endpoint")
    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "NOT_FOUND"
    assert "message" in data["error"]
    assert "request_id" in data["error"]
    assert data["error"]["request_id"] == response.headers.get("X-Request-ID")


def test_app_error_handling(client: TestClient) -> None:
    """Verify custom AppError produces the expected response format and status."""

    @app.get("/test-app-error")
    def trigger_app_error() -> None:
        raise AppError(code="TEST_ERROR", message="Test error description", status_code=400)

    response = client.get("/test-app-error")
    assert response.status_code == 400
    data = response.json()
    assert data["error"]["code"] == "TEST_ERROR"
    assert data["error"]["message"] == "Test error description"
    assert "request_id" in data["error"]


def test_settings_repr_masks_database_url() -> None:
    """Verify Settings __repr__ and __str__ never expose DATABASE_URL."""
    from app.core.config import Settings

    custom_settings = Settings(
        DATABASE_URL="postgresql+psycopg://secret_user:secret_pass@db:5432/db"
    )
    repr_str = repr(custom_settings)
    assert "secret_pass" not in repr_str
    assert "***" in repr_str
    assert str(custom_settings) == repr_str


def test_settings_fail_fast_when_database_url_missing() -> None:
    """Verify Settings raises ValueError when DATABASE_URL is missing outside test mode."""
    import os
    import sys

    from app.core.config import Settings

    pytest_marker = os.environ.pop("PYTEST_CURRENT_TEST", None)
    pytest_mod = sys.modules.pop("pytest", None)
    try:
        with pytest.raises(ValueError, match="DATABASE_URL is missing or empty"):
            Settings(DATABASE_URL="", LOCAL_DB_PASSWORD="", APP_ENV="dev")
    finally:
        if pytest_marker is not None:
            os.environ["PYTEST_CURRENT_TEST"] = pytest_marker
        if pytest_mod is not None:
            sys.modules["pytest"] = pytest_mod


def test_ids_generate_id() -> None:
    """Verify opaque ID generation with expected prefix and randomness."""
    from app.core.ids import generate_id

    user_id = generate_id("usr")
    assert user_id.startswith("usr_")
    assert len(user_id) > 10

    group_id = generate_id("grp")
    assert group_id.startswith("grp_")
    assert user_id != group_id


def test_validation_error_format(client: TestClient) -> None:
    """Verify Pydantic validation errors return 422 with standard error envelope."""
    from pydantic import BaseModel

    class DummyPayload(BaseModel):
        count: int

    @app.post("/test-validation")
    def trigger_validation(payload: DummyPayload) -> dict[str, int]:
        return {"count": payload.count}

    response = client.post("/test-validation", json={"count": "not-an-integer"})
    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert "request_id" in data["error"]


def test_unhandled_exception_returns_500() -> None:
    """Verify unhandled exceptions return 500 without leaking stack trace."""
    no_raise_client = TestClient(app, raise_server_exceptions=False)

    @app.get("/test-unhandled")
    def trigger_crash() -> None:
        raise RuntimeError("Something exploded unexpectedly")

    response = no_raise_client.get("/test-unhandled")
    assert response.status_code == 500
    data = response.json()
    assert data["error"]["code"] == "INTERNAL_SERVER_ERROR"
    assert data["error"]["message"] == "An internal server error occurred"
    assert "request_id" in data["error"]
