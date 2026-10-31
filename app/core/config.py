import os
import sys
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REQUIRED_SECRET_KEYS: list[str] = [
    "WEBHOOK_HMAC_KEY",
    "WEBHOOK_KEY_ID",
    "AUDIT_HMAC_KEY",
    "AUDIT_KEY_ID",
    "PII_ENC_KEY",
    "PII_BLIND_INDEX_KEY",
    "PII_KEY_ID",
]

HEX_32_BYTE_KEYS: list[str] = [
    "WEBHOOK_HMAC_KEY",
    "AUDIT_HMAC_KEY",
    "PII_ENC_KEY",
    "PII_BLIND_INDEX_KEY",
]

TEST_FALLBACK_SECRETS: dict[str, str] = {
    "WEBHOOK_HMAC_KEY": "11" * 32,
    "WEBHOOK_KEY_ID": "wh_test_key",
    "AUDIT_HMAC_KEY": "22" * 32,
    "AUDIT_KEY_ID": "audit_test_key",
    "PII_ENC_KEY": "33" * 32,
    "PII_BLIND_INDEX_KEY": "44" * 32,
    "PII_KEY_ID": "pii_test_key",
}


def _normalize_db_url(url: str) -> str:
    """Normalize legacy postgres:// or standard postgresql:// to postgresql+psycopg://."""
    if not url:
        return url
    trimmed = url.strip()
    if trimmed.startswith("postgres://"):
        return "postgresql+psycopg://" + trimmed[len("postgres://") :]
    if trimmed.startswith("postgresql://"):
        return "postgresql+psycopg://" + trimmed[len("postgresql://") :]
    return trimmed


class Settings(BaseSettings):
    DATABASE_URL: str = ""
    MIGRATION_DATABASE_URL: str = ""
    TEST_DATABASE_URL: str = ""
    LOCAL_DB_PASSWORD: str = ""
    APP_ENV: Literal["dev", "test", "demo", "prod"] = "dev"

    # Edge hardening & Rate limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_USER_REGISTRATION: str = "5/minute"
    RATE_LIMIT_AUTHENTICATED: str = "60/minute"
    RATE_LIMIT_SETTLEMENTS: str = "10/minute"
    MAX_REQUEST_BODY_BYTES: int = 65536  # 64 KB
    TRUSTED_PROXY_HOPS: int | None = None

    # Webhook HMAC Configuration (Mock Payment Provider)
    # Zero fallback defaults in dev/demo/prod
    WEBHOOK_HMAC_KEY: str = ""
    WEBHOOK_KEY_ID: str = ""

    # Audit HMAC Configuration (Tamper-evident ledger hash chain)
    # Zero fallback defaults in dev/demo/prod
    AUDIT_HMAC_KEY: str = ""
    AUDIT_KEY_ID: str = ""

    # PII Encryption & Blind Index Configuration (AES-256-GCM + Blind Index)
    # Zero fallback defaults in dev/demo/prod
    PII_ENC_KEY: str = ""
    PII_BLIND_INDEX_KEY: str = ""
    PII_KEY_ID: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_config(self) -> "Settings":
        """Fail fast outside tests if DATABASE_URL or secrets are missing/invalid."""
        if not self.DATABASE_URL.strip() and self.LOCAL_DB_PASSWORD.strip():
            self.DATABASE_URL = (
                f"postgresql+psycopg://postgres:{self.LOCAL_DB_PASSWORD}@localhost:5432/akira"
            )
        if not self.TEST_DATABASE_URL.strip() and self.LOCAL_DB_PASSWORD.strip():
            self.TEST_DATABASE_URL = (
                f"postgresql+psycopg://postgres:{self.LOCAL_DB_PASSWORD}@localhost:5432/akira_test"
            )

        self.DATABASE_URL = _normalize_db_url(self.DATABASE_URL)
        self.MIGRATION_DATABASE_URL = _normalize_db_url(self.MIGRATION_DATABASE_URL)
        self.TEST_DATABASE_URL = _normalize_db_url(self.TEST_DATABASE_URL)

        if self.TRUSTED_PROXY_HOPS is None:
            self.TRUSTED_PROXY_HOPS = 1 if self.APP_ENV in ("demo", "prod") else 0

        # Detect Alembic migration context: migrations only need MIGRATION_DATABASE_URL
        is_alembic = (
            os.getenv("ALEMBIC_MIGRATION_RUNNING") == "1"
            or os.getenv("ALEMBIC_CONTEXT") == "1"
            or (len(sys.argv) > 0 and "alembic" in os.path.basename(sys.argv[0]).lower())
        )

        is_test = self.APP_ENV == "test"

        if is_test:
            # Test profile: populate deterministic fallback secrets if omitted
            for key, default_val in TEST_FALLBACK_SECRETS.items():
                if not getattr(self, key, "").strip():
                    setattr(self, key, default_val)
        elif not is_alembic:
            # dev / demo / prod outside Alembic: all cryptographic keys and key IDs are mandatory
            missing = [k for k in REQUIRED_SECRET_KEYS if not getattr(self, k, "").strip()]
            if missing:
                raise ValueError(
                    f"Missing required security environment variable(s): {', '.join(missing)}. "
                    f"In '{self.APP_ENV}' environment, all cryptographic keys and key IDs "
                    "must be explicitly set."
                )

            # Validate key format and 32-byte length (64 hex characters)
            for key_name in HEX_32_BYTE_KEYS:
                val = getattr(self, key_name).strip()
                if len(val) != 64:
                    raise ValueError(
                        f"Invalid key length for {key_name}: expected 32 bytes "
                        f"(64 hex characters), got {len(val)} characters."
                    )
                try:
                    raw_bytes = bytes.fromhex(val)
                    if len(raw_bytes) != 32:
                        raise ValueError(
                            f"Invalid key length for {key_name}: expected 32 bytes, "
                            f"got {len(raw_bytes)} bytes."
                        )
                except ValueError as err:
                    if "Invalid key length" not in str(err):
                        raise ValueError(
                            f"Invalid key format for {key_name}: "
                            "must be a valid 32-byte hex-encoded string."
                        ) from None
                    raise

        # Enforce DATABASE_URL presence for API runtime outside tests and Alembic
        if not is_test and not is_alembic and not self.DATABASE_URL.strip():
            raise ValueError(
                "DATABASE_URL is missing or empty. A valid PostgreSQL connection string "
                "must be provided via environment variable or .env file."
            )

        return self

    def __repr__(self) -> str:
        """Never log secrets or full connection strings in logs or debug representations."""
        return (
            f"Settings(APP_ENV={self.APP_ENV!r}, DB='***', "
            f"WH_KID={self.WEBHOOK_KEY_ID!r}, AUDIT_KID={self.AUDIT_KEY_ID!r}, "
            f"PII_KID={self.PII_KEY_ID!r})"
        )

    def __str__(self) -> str:
        return self.__repr__()


settings = Settings()
