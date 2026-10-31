import os
import sys
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    WEBHOOK_HMAC_KEY: str = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    WEBHOOK_KEY_ID: str = "wh_dev_key"

    # Audit HMAC Configuration (Tamper-evident ledger hash chain)
    AUDIT_HMAC_KEY: str = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    AUDIT_KEY_ID: str = "audit_dev_key"

    # PII Encryption & Blind Index Configuration (AES-256-GCM + Blind Index)
    PII_ENC_KEY: str = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    PII_BLIND_INDEX_KEY: str = "fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210"
    PII_KEY_ID: str = "pii_dev_key"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_database_url(self) -> "Settings":
        """Fail fast outside tests if DATABASE_URL is missing or empty."""
        if not self.DATABASE_URL.strip() and self.LOCAL_DB_PASSWORD.strip():
            self.DATABASE_URL = (
                f"postgresql+psycopg://postgres:{self.LOCAL_DB_PASSWORD}@localhost:5432/akira"
            )
        if not self.TEST_DATABASE_URL.strip() and self.LOCAL_DB_PASSWORD.strip():
            self.TEST_DATABASE_URL = (
                f"postgresql+psycopg://postgres:{self.LOCAL_DB_PASSWORD}@localhost:5432/akira_test"
            )

        if self.TRUSTED_PROXY_HOPS is None:
            self.TRUSTED_PROXY_HOPS = 1 if self.APP_ENV in ("demo", "prod") else 0

        is_test = (
            self.APP_ENV == "test" or "pytest" in sys.modules or "PYTEST_CURRENT_TEST" in os.environ
        )
        if not is_test and not self.DATABASE_URL.strip():
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
