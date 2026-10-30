"""Pure domain logic for tamper-evident ledger HMAC hash chaining."""

import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Any

GENESIS_PREV_HASH: str = "0" * 64


def canonical_json(data: Any) -> str:
    """Format data into deterministic canonical JSON:
    - Sorted dictionary keys (recursively)
    - No whitespace between tokens (separators=(',', ':'))
    - Datetimes formatted as ISO-8601 UTC ('YYYY-MM-DDTHH:MM:SSZ' or '+00:00')
    """

    def _default(obj: Any) -> str:
        if isinstance(obj, datetime):
            dt = obj.replace(tzinfo=UTC) if obj.tzinfo is None else obj.astimezone(UTC)
            return str(dt.isoformat())
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=_default)


def compute_entry_hash(
    secret_hex: str,
    prev_hash: str,
    canonical_entry_str: str,
) -> str:
    """Compute HMAC-SHA256(secret, prev_hash || '|' || canonical_entry)."""
    key_bytes = bytes.fromhex(secret_hex)
    message = f"{prev_hash}|{canonical_entry_str}".encode()
    return hmac.new(key_bytes, message, hashlib.sha256).hexdigest()
