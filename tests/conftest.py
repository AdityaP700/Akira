"""Global pytest fixtures and configuration for PostgreSQL 16 test suite."""

import os

os.environ.setdefault("APP_ENV", "test")

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_db
from app.core.config import settings
from app.security.ratelimit import limiter

# -----------------------------------------------------------------------------
# Fail-Fast Enforcement: Tests MUST run on real PostgreSQL 16 (TEST_DATABASE_URL).
# SQLite fallback is strictly forbidden by project guardrails and assignment brief.
# -----------------------------------------------------------------------------
if not settings.TEST_DATABASE_URL or "sqlite" in settings.TEST_DATABASE_URL.lower():
    raise RuntimeError(
        "TEST_DATABASE_URL must be a PostgreSQL connection string. "
        "SQLite is strictly forbidden for integration, API, and concurrency tests."
    )

try:
    _probe_engine = create_engine(
        settings.TEST_DATABASE_URL, pool_pre_ping=True, connect_args={"connect_timeout": 3}
    )
    with _probe_engine.connect() as _conn:
        _conn.execute(text("SELECT 1;"))
    _probe_engine.dispose()
except Exception as e:
    raise RuntimeError(
        f"PostgreSQL test database at {settings.TEST_DATABASE_URL} is unreachable: {e}. "
        "Tests must run on real PostgreSQL 16 and cannot fall back to SQLite."
    ) from e

# Ensure migration test database exists for test_migrations.py
try:
    with create_engine(settings.TEST_DATABASE_URL, isolation_level="AUTOCOMMIT").connect() as _conn:
        _mig_db_exists = _conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = 'akira_migration_test';")
        ).scalar()
        if not _mig_db_exists:
            _conn.execute(text("CREATE DATABASE akira_migration_test;"))
except Exception:  # noqa: S110
    pass


@pytest.fixture(scope="session")
def postgres_engine():
    """Session-scoped PostgreSQL engine connected to TEST_DATABASE_URL."""
    engine = create_engine(
        settings.TEST_DATABASE_URL,
        pool_size=30,
        max_overflow=20,
        pool_pre_ping=True,
    )
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def session_factory(postgres_engine) -> sessionmaker:
    """Session-scoped session factory bound to the PostgreSQL engine."""
    return sessionmaker(bind=postgres_engine, autoflush=False, autocommit=False)


@pytest.fixture(autouse=True)
def clean_postgres_db(postgres_engine) -> Generator[None, None, None]:
    """Truncate all application tables before each test to guarantee complete test isolation.

    Fast (~5ms) table truncation preserving schema structure and resetting identities.
    """
    with postgres_engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE TABLE users, groups, group_members, expenses, expense_shares, "
                "settlements, ledger_entries, idempotency_keys, notifications, user_pii "
                "RESTART IDENTITY CASCADE;"
            )
        )
    yield


@pytest.fixture(autouse=True)
def manage_rate_limiting() -> Generator[None, None, None]:
    """Disable rate limiting by default so setup requests do not exhaust limits.

    Tests that specifically verify rate limiting will re-enable limiter.enabled explicitly.
    """
    prev_enabled = limiter.enabled
    limiter.enabled = False
    try:
        yield
    finally:
        limiter.enabled = prev_enabled


@pytest.fixture
def db_session(session_factory: sessionmaker) -> Generator[Session, None, None]:
    """Provide a clean PostgreSQL session for unit/repository tests."""
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client_and_session(
    session_factory: sessionmaker,
) -> Generator[tuple[TestClient, Session], None, None]:
    """Provide a TestClient with get_db overridden to use real PostgreSQL."""
    from app.main import app

    def override_get_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    test_session = session_factory()
    try:
        yield client, test_session
    finally:
        test_session.close()
        app.dependency_overrides.clear()
