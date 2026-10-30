"""Key provider adapter interface and implementations."""

from typing import Protocol

from app.core.config import settings


class KeyProvider(Protocol):
    """Protocol for cryptographic key resolution supporting key rotation."""

    def get_webhook_key(self, kid: str) -> str | None:
        """Return the hex secret for a given key ID, or None if unknown."""
        ...

    def get_current_webhook_key(self) -> tuple[str, str]:
        """Return the current (kid, secret_hex) used for webhook signing."""
        ...

    def get_audit_key(self, kid: str) -> str | None:
        """Return the audit hex secret for a given key ID, or None if unknown."""
        ...

    def get_current_audit_key(self) -> tuple[str, str]:
        """Return the current (kid, secret_hex) used for audit HMAC hashing."""
        ...

    def get_encryption_key(self, kid: str) -> str | None:
        """Return the AES-256 hex key for a given PII key ID, or None if unknown."""
        ...

    def get_blind_index_key(self, kid: str) -> str | None:
        """Return the HMAC-SHA256 hex key for a given blind index key ID, or None."""
        ...

    def get_current_pii_key(self) -> tuple[str, str, str]:
        """Return the current (kid, enc_key_hex, blind_key_hex) for PII operations."""
        ...


class EnvKeyProvider:
    """Key provider reading secrets from configuration / environment.

    Production Replacement Note:
    In enterprise production deployments, this adapter should be replaced by a KMS
    provider (e.g. AWS KMS, Google Cloud KMS, or HashiCorp Vault) using envelope
    encryption:
    1. A Key Management Service generates and manages a Master Key (KKEK).
    2. Data Encryption Keys (DEKs) are generated locally or requested per-user/per-tenant,
       and the encrypted DEK is stored alongside the ciphertext.
    3. Rotation is handled seamlessly by re-wrapping DEKs or rotating active key IDs.
    """

    def __init__(
        self,
        key_id: str | None = None,
        secret_hex: str | None = None,
        audit_key_id: str | None = None,
        audit_secret_hex: str | None = None,
        pii_key_id: str | None = None,
        pii_enc_hex: str | None = None,
        pii_blind_hex: str | None = None,
    ) -> None:
        self._key_id = key_id or settings.WEBHOOK_KEY_ID
        self._secret_hex = secret_hex or settings.WEBHOOK_HMAC_KEY
        # Multi-key dictionary for webhook rotation support
        self._keys: dict[str, str] = {
            settings.WEBHOOK_KEY_ID: settings.WEBHOOK_HMAC_KEY,
            self._key_id: self._secret_hex,
        }

        self._audit_key_id = audit_key_id or settings.AUDIT_KEY_ID
        self._audit_secret_hex = audit_secret_hex or settings.AUDIT_HMAC_KEY
        # Multi-key dictionary for audit rotation support
        self._audit_keys: dict[str, str] = {
            settings.AUDIT_KEY_ID: settings.AUDIT_HMAC_KEY,
            self._audit_key_id: self._audit_secret_hex,
        }

        self._pii_key_id = pii_key_id or settings.PII_KEY_ID
        self._pii_enc_hex = pii_enc_hex or settings.PII_ENC_KEY
        self._pii_blind_hex = pii_blind_hex or settings.PII_BLIND_INDEX_KEY
        self._pii_enc_keys: dict[str, str] = {
            settings.PII_KEY_ID: settings.PII_ENC_KEY,
            self._pii_key_id: self._pii_enc_hex,
        }
        self._pii_blind_keys: dict[str, str] = {
            settings.PII_KEY_ID: settings.PII_BLIND_INDEX_KEY,
            self._pii_key_id: self._pii_blind_hex,
        }

    def register_key(self, kid: str, secret_hex: str) -> None:
        """Register an additional webhook key for rotation support."""
        self._keys[kid] = secret_hex

    def register_audit_key(self, kid: str, secret_hex: str) -> None:
        """Register an additional audit key for rotation support."""
        self._audit_keys[kid] = secret_hex

    def register_pii_keys(self, kid: str, enc_hex: str, blind_hex: str) -> None:
        """Register an additional PII key pair for rotation support."""
        self._pii_enc_keys[kid] = enc_hex
        self._pii_blind_keys[kid] = blind_hex

    def get_webhook_key(self, kid: str) -> str | None:
        return self._keys.get(kid)

    def get_current_webhook_key(self) -> tuple[str, str]:
        return self._key_id, self._secret_hex

    def get_audit_key(self, kid: str) -> str | None:
        return self._audit_keys.get(kid)

    def get_current_audit_key(self) -> tuple[str, str]:
        return self._audit_key_id, self._audit_secret_hex

    def get_encryption_key(self, kid: str) -> str | None:
        return self._pii_enc_keys.get(kid)

    def get_blind_index_key(self, kid: str) -> str | None:
        return self._pii_blind_keys.get(kid)

    def get_current_pii_key(self) -> tuple[str, str, str]:
        return self._pii_key_id, self._pii_enc_hex, self._pii_blind_hex
