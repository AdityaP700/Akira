from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/akira"
    APP_ENV: Literal["dev", "test", "prod"] = "dev"

    # Edge hardening & Rate limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_USER_REGISTRATION: str = "5/minute"
    RATE_LIMIT_AUTHENTICATED: str = "60/minute"
    RATE_LIMIT_SETTLEMENTS: str = "10/minute"
    MAX_REQUEST_BODY_BYTES: int = 65536  # 64 KB

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
