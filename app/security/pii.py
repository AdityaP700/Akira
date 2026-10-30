"""Application-level PII encryption and blind indexing.

Implements AES-256-GCM authenticated encryption with associated data (AEAD)
and HMAC-SHA256 blind indexing for sensitive identifiers (VPAs).

Guardrails:
- P6: PII (VPA) encrypted at application level; responses show masked values only.
- Associated data binds ciphertext to user public ID (preventing ciphertext transplant).
- Blind index allows O(1) exact-match lookups and unique constraints without decrypting rows.
"""

import hashlib
import hmac
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class PiiCryptoError(Exception):
    """Base error for PII cryptographic operations."""

    pass


class PiiDecryptionError(PiiCryptoError):
    """Raised when ciphertext decryption or authentication tag validation fails."""

    pass


def normalise_vpa(vpa: str) -> str:
    """Normalise VPA for deterministic blind indexing (lowercase and stripped)."""
    return vpa.strip().lower()


def compute_blind_index(blind_key_bytes: bytes, vpa: str) -> str:
    """Compute HMAC-SHA256 blind index for exact match searchability.

    Formula: HMAC-SHA256(blind_key, normalise(vpa))
    """
    normalised = normalise_vpa(vpa).encode("utf-8")
    return hmac.new(blind_key_bytes, normalised, hashlib.sha256).hexdigest()


def encrypt_vpa(
    key_bytes: bytes,
    plaintext: str,
    associated_data: str,
    nonce: bytes | None = None,
) -> tuple[bytes, bytes]:
    """Encrypt a VPA string using AES-256-GCM.

    Args:
        key_bytes: 32-byte AES key.
        plaintext: Raw VPA string.
        associated_data: User public ID (e.g. 'usr_...') bound as authenticated data.
        nonce: Optional 12-byte nonce (generated with os.urandom(12) if omitted).

    Returns:
        tuple of (ciphertext, nonce)
    """
    if len(key_bytes) != 32:
        raise PiiCryptoError("AES-256 key must be exactly 32 bytes")

    if nonce is None:
        nonce = os.urandom(12)
    elif len(nonce) != 12:
        raise PiiCryptoError("GCM nonce must be exactly 12 bytes (96 bits)")

    aesgcm = AESGCM(key_bytes)
    data = plaintext.encode("utf-8")
    aad = associated_data.encode("utf-8")
    ciphertext = aesgcm.encrypt(nonce, data, aad)
    return ciphertext, nonce


def decrypt_vpa(
    key_bytes: bytes,
    ciphertext: bytes,
    nonce: bytes,
    associated_data: str,
) -> str:
    """Decrypt an AES-256-GCM encrypted VPA.

    Args:
        key_bytes: 32-byte AES key.
        ciphertext: Encrypted ciphertext including 16-byte authentication tag.
        nonce: 12-byte nonce used during encryption.
        associated_data: User public ID (e.g. 'usr_...') bound during encryption.

    Returns:
        Decrypted plaintext VPA string.

    Raises:
        PiiDecryptionError: If the authentication tag fails (tampered ciphertext or wrong AAD).
    """
    if len(key_bytes) != 32:
        raise PiiCryptoError("AES-256 key must be exactly 32 bytes")

    aesgcm = AESGCM(key_bytes)
    aad = associated_data.encode("utf-8")
    try:
        decrypted_bytes = aesgcm.decrypt(nonce, ciphertext, aad)
        return decrypted_bytes.decode("utf-8")
    except InvalidTag as exc:
        raise PiiDecryptionError(
            "PII decryption failed: invalid authentication tag or associated data"
        ) from exc


def mask_vpa(vpa: str) -> str:
    """Mask a VPA for safe display in logs and API responses.

    Example:
        'alice@okhdfcbank' -> 'al***@okhdfcbank'
        'bob@upi'          -> 'bo***@upi'
        'a@upi'            -> 'a***@upi'
    """
    cleaned = vpa.strip()
    if "@" not in cleaned:
        return "***"

    username, domain = cleaned.split("@", 1)
    if len(username) <= 2:
        masked_user = f"{username[:1]}***"
    else:
        masked_user = f"{username[:2]}***"

    return f"{masked_user}@{domain}"
