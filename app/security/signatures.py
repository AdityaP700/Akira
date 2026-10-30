"""HMAC signature verification for webhook integrity."""

import hashlib
import hmac
import time

from app.adapters.keys import KeyProvider
from app.core.errors import (
    InvalidSignatureError,
    StaleTimestampError,
    UnknownKeyIdError,
)


def compute_signature(secret_hex: str, timestamp: int, raw_body: bytes) -> str:
    """Compute HMAC-SHA256 over f"{timestamp}.{raw_body}"."""
    payload = f"{timestamp}.".encode() + raw_body
    secret_bytes = bytes.fromhex(secret_hex)
    return hmac.new(secret_bytes, payload, hashlib.sha256).hexdigest()


def build_signature_header(
    kid: str,
    secret_hex: str,
    raw_body: bytes,
    timestamp: int | None = None,
) -> str:
    """Build the X-Provider-Signature header value: kid=<id>,t=<unix>,v1=<hex>."""
    t = timestamp if timestamp is not None else int(time.time())
    v1 = compute_signature(secret_hex, t, raw_body)
    return f"kid={kid},t={t},v1={v1}"


def parse_signature_header(header_value: str) -> dict[str, str]:
    """Parse comma-separated key=value pairs from the signature header."""
    parts: dict[str, str] = {}
    for item in header_value.split(","):
        if "=" in item:
            k, v = item.split("=", 1)
            parts[k.strip()] = v.strip()
    return parts


def verify_webhook_signature(
    raw_body: bytes,
    signature_header: str | None,
    key_provider: KeyProvider,
    tolerance_seconds: int = 300,
    current_time: int | None = None,
) -> None:
    """Verify webhook signature according to OWASP API10 and payment provider specifications.

    Header format: X-Provider-Signature: kid=<id>,t=<unix>,v1=<hex>
    - Raw body HMAC-SHA256 verification
    - Timestamp window validation |now - t| <= tolerance_seconds (default 300s)
    - Constant-time comparison using hmac.compare_digest
    - Unknown kid raises UnknownKeyIdError (HTTP 401)
    - Stale timestamp raises StaleTimestampError (HTTP 401)
    - Invalid signature raises InvalidSignatureError (HTTP 401)
    """
    if not signature_header:
        raise InvalidSignatureError("Missing X-Provider-Signature header")

    parsed = parse_signature_header(signature_header)
    kid = parsed.get("kid")
    t_str = parsed.get("t")
    v1 = parsed.get("v1")

    if not kid or not t_str or not v1:
        raise InvalidSignatureError("Malformed X-Provider-Signature header")

    try:
        t = int(t_str)
    except ValueError:
        raise InvalidSignatureError("Invalid timestamp in signature header") from None

    now = current_time if current_time is not None else int(time.time())
    if abs(now - t) > tolerance_seconds:
        raise StaleTimestampError(f"Timestamp outside tolerance window of {tolerance_seconds}s")

    secret_hex = key_provider.get_webhook_key(kid)
    if secret_hex is None:
        raise UnknownKeyIdError(f"Unknown webhook key identifier: {kid}")

    expected_signature = compute_signature(secret_hex, t, raw_body)
    if not hmac.compare_digest(expected_signature, v1):
        raise InvalidSignatureError("Webhook signature verification failed")
