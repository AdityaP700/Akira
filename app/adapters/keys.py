"""Key provider adapter interface and implementations."""

from typing import Protocol

from app.core.config import settings


class KeyProvider(Protocol):
    """Protocol for cryptographic key resolution supporting key rotation."""

    def get_webhook_key(self, kid: str) -> str | None:
        """Return the hex secret for a given key ID, or None if unknown."""
        ...

    def get_current_webhook_key(self) -> tuple[str, str]:
        """Return the current (kid, secret_hex) used for signing."""
        ...


class EnvKeyProvider:
    """Key provider reading secrets from configuration / environment."""

    def __init__(self, key_id: str | None = None, secret_hex: str | None = None) -> None:
        self._key_id = key_id or settings.WEBHOOK_KEY_ID
        self._secret_hex = secret_hex or settings.WEBHOOK_HMAC_KEY
        # Multi-key dictionary for rotation support
        self._keys: dict[str, str] = {self._key_id: self._secret_hex}

    def register_key(self, kid: str, secret_hex: str) -> None:
        """Register an additional key for rotation support."""
        self._keys[kid] = secret_hex

    def get_webhook_key(self, kid: str) -> str | None:
        return self._keys.get(kid)

    def get_current_webhook_key(self) -> tuple[str, str]:
        return self._key_id, self._secret_hex
