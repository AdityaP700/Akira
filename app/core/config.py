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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def __repr__(self) -> str:
        """Never log secrets or full connection strings in logs or debug representations."""
        return f"Settings(APP_ENV={self.APP_ENV!r}, DATABASE_URL='***')"

    def __str__(self) -> str:
        return self.__repr__()


settings = Settings()
