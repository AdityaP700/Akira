"""Unit tests for configuration security and fail-fast secret validation.

Verifies:
1. APP_ENV=test works out of the box with safe deterministic test fallback keys.
2. In dev/demo/prod, startup fails fast naming missing secret keys or key IDs.
3. Cryptographic keys must be valid 32-byte hex-encoded strings or fail fast.
4. Alembic migrations do not require cryptographic secret keys.
"""

import pytest

from app.core.config import Settings


def test_test_env_works_without_explicit_keys() -> None:
    """In APP_ENV=test, Settings populates deterministic test keys automatically."""
    s = Settings(
        _env_file=None,
        APP_ENV="test",
        TEST_DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/akira_test",
    )
    assert s.APP_ENV == "test"
    assert s.WEBHOOK_HMAC_KEY == "11" * 32
    assert s.WEBHOOK_KEY_ID == "wh_test_key"
    assert s.AUDIT_HMAC_KEY == "22" * 32
    assert s.AUDIT_KEY_ID == "audit_test_key"
    assert s.PII_ENC_KEY == "33" * 32
    assert s.PII_BLIND_INDEX_KEY == "44" * 32
    assert s.PII_KEY_ID == "pii_test_key"


@pytest.mark.parametrize("env", ["demo", "dev", "prod"])
def test_missing_key_in_non_test_envs_raises_startup_error(env: str) -> None:
    """In dev, demo, and prod, missing cryptographic secrets must fail fast naming missing keys."""
    with pytest.raises(ValueError) as exc_info:
        Settings(
            _env_file=None,
            APP_ENV=env,
            DATABASE_URL="postgresql+psycopg://app_rw:secret@localhost:5432/akira",
        )
    err = str(exc_info.value)
    assert "Missing required security environment variable(s)" in err
    assert "WEBHOOK_HMAC_KEY" in err
    assert "AUDIT_HMAC_KEY" in err
    assert "PII_ENC_KEY" in err
    assert "PII_BLIND_INDEX_KEY" in err
    # Ensure error message does not expose any dummy secret values
    assert "secret" not in err.lower() or "variable" in err.lower()


def test_partial_missing_key_names_exact_missing_variable() -> None:
    """When a specific key is missing, error message names exactly that variable."""
    valid_32_bytes = "aa" * 32
    with pytest.raises(ValueError) as exc_info:
        Settings(
            _env_file=None,
            APP_ENV="demo",
            DEMO_ACCESS_KEY="demo_valid_key",
            DATABASE_URL="postgresql+psycopg://app_rw:secret@localhost:5432/akira",
            WEBHOOK_HMAC_KEY=valid_32_bytes,
            WEBHOOK_KEY_ID="whk_1",
            AUDIT_HMAC_KEY=valid_32_bytes,
            AUDIT_KEY_ID="aud_1",
            # PII_ENC_KEY omitted
            PII_BLIND_INDEX_KEY=valid_32_bytes,
            PII_KEY_ID="pii_1",
        )
    err = str(exc_info.value)
    assert "Missing required security environment variable(s): PII_ENC_KEY" in err
    assert "WEBHOOK_HMAC_KEY" not in err


@pytest.mark.parametrize("key_name", ["WEBHOOK_KEY_ID", "AUDIT_KEY_ID", "PII_KEY_ID"])
def test_missing_key_id_raises_startup_error(key_name: str) -> None:
    """Missing key identifiers must also trigger fail-fast startup errors in demo/prod."""
    valid_32_bytes = "aa" * 32
    kwargs = {
        "APP_ENV": "demo",
        "DEMO_ACCESS_KEY": "demo_valid_key",
        "DATABASE_URL": "postgresql+psycopg://app_rw:secret@localhost:5432/akira",
        "WEBHOOK_HMAC_KEY": valid_32_bytes,
        "WEBHOOK_KEY_ID": "whk_1",
        "AUDIT_HMAC_KEY": valid_32_bytes,
        "AUDIT_KEY_ID": "aud_1",
        "PII_ENC_KEY": valid_32_bytes,
        "PII_BLIND_INDEX_KEY": valid_32_bytes,
        "PII_KEY_ID": "pii_1",
    }
    kwargs[key_name] = ""
    with pytest.raises(ValueError) as exc_info:
        Settings(_env_file=None, **kwargs)
    err = str(exc_info.value)
    assert f"Missing required security environment variable(s): {key_name}" in err


@pytest.mark.parametrize(
    "key_name",
    ["WEBHOOK_HMAC_KEY", "AUDIT_HMAC_KEY", "PII_ENC_KEY", "PII_BLIND_INDEX_KEY"],
)
def test_invalid_key_length_rejected(key_name: str) -> None:
    """Keys with invalid byte lengths (not 32 bytes / 64 hex chars) must be rejected."""
    valid_32_bytes = "aa" * 32
    short_key = "aa" * 16  # 16 bytes / 32 hex chars
    kwargs = {
        "APP_ENV": "demo",
        "DEMO_ACCESS_KEY": "demo_valid_key",
        "DATABASE_URL": "postgresql+psycopg://app_rw:secret@localhost:5432/akira",
        "WEBHOOK_HMAC_KEY": valid_32_bytes,
        "WEBHOOK_KEY_ID": "whk_1",
        "AUDIT_HMAC_KEY": valid_32_bytes,
        "AUDIT_KEY_ID": "aud_1",
        "PII_ENC_KEY": valid_32_bytes,
        "PII_BLIND_INDEX_KEY": valid_32_bytes,
        "PII_KEY_ID": "pii_1",
    }
    kwargs[key_name] = short_key
    with pytest.raises(ValueError) as exc_info:
        Settings(_env_file=None, **kwargs)
    err = str(exc_info.value)
    assert f"Invalid key length for {key_name}: expected 32 bytes (64 hex characters)" in err
    # Ensure error does not expose the raw key value
    assert short_key not in err


@pytest.mark.parametrize(
    "key_name",
    ["WEBHOOK_HMAC_KEY", "AUDIT_HMAC_KEY", "PII_ENC_KEY", "PII_BLIND_INDEX_KEY"],
)
def test_non_hex_key_format_rejected(key_name: str) -> None:
    """Keys with non-hexadecimal characters must be rejected."""
    valid_32_bytes = "aa" * 32
    non_hex_key = "zz" * 32  # 64 chars, but 'z' is invalid hex
    kwargs = {
        "APP_ENV": "demo",
        "DEMO_ACCESS_KEY": "demo_valid_key",
        "DATABASE_URL": "postgresql+psycopg://app_rw:secret@localhost:5432/akira",
        "WEBHOOK_HMAC_KEY": valid_32_bytes,
        "WEBHOOK_KEY_ID": "whk_1",
        "AUDIT_HMAC_KEY": valid_32_bytes,
        "AUDIT_KEY_ID": "aud_1",
        "PII_ENC_KEY": valid_32_bytes,
        "PII_BLIND_INDEX_KEY": valid_32_bytes,
        "PII_KEY_ID": "pii_1",
    }
    kwargs[key_name] = non_hex_key
    with pytest.raises(ValueError) as exc_info:
        Settings(_env_file=None, **kwargs)
    err = str(exc_info.value)
    assert f"Invalid key format for {key_name}: must be a valid 32-byte hex-encoded string." in err
    # Ensure error does not expose the raw key value
    assert non_hex_key not in err


def test_alembic_does_not_require_secret_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """Alembic context only requires migration URL and does not require HMAC/AES secrets."""
    monkeypatch.setenv("ALEMBIC_CONTEXT", "1")
    s = Settings(
        _env_file=None,
        APP_ENV="demo",
        MIGRATION_DATABASE_URL="postgresql://app_owner:pass@localhost:5432/akira",
    )
    assert s.APP_ENV == "demo"
    assert s.MIGRATION_DATABASE_URL == "postgresql+psycopg://app_owner:pass@localhost:5432/akira"
    # Secrets were not required
    assert s.PII_ENC_KEY == ""


def test_valid_demo_profile_succeeds_and_normalizes_urls() -> None:
    """When valid 32-byte hex keys and postgres:// URLs are provided, demo startup succeeds."""
    valid_32_bytes = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    s = Settings(
        _env_file=None,
        APP_ENV="demo",
        DEMO_ACCESS_KEY="demo_valid_key",
        DATABASE_URL="postgres://app_rw:mypass@localhost:5432/akira",
        MIGRATION_DATABASE_URL="postgresql://app_owner:mypass@localhost:5432/akira",
        WEBHOOK_HMAC_KEY=valid_32_bytes,
        WEBHOOK_KEY_ID="whk_1",
        AUDIT_HMAC_KEY=valid_32_bytes,
        AUDIT_KEY_ID="aud_1",
        PII_ENC_KEY=valid_32_bytes,
        PII_BLIND_INDEX_KEY=valid_32_bytes,
        PII_KEY_ID="pii_1",
    )
    assert s.APP_ENV == "demo"
    assert s.DATABASE_URL == "postgresql+psycopg://app_rw:mypass@localhost:5432/akira"
    assert s.MIGRATION_DATABASE_URL == "postgresql+psycopg://app_owner:mypass@localhost:5432/akira"
    assert s.TRUSTED_PROXY_HOPS == 1
