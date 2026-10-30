"""Opaque keyset pagination utilities."""

import base64
from datetime import datetime

from app.core.errors import ValidationError


def encode_cursor(created_at: datetime, item_id: int) -> str:
    """Encode created_at timestamp and item_id into an opaque URL-safe base64 cursor."""
    payload = f"{created_at.isoformat()}|{item_id}"
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("utf-8")


def decode_cursor(cursor: str) -> tuple[datetime, int]:
    """Decode an opaque URL-safe base64 cursor into (created_at, item_id).

    Raises:
        ValidationError: If cursor cannot be decoded or is malformed.
    """
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("utf-8")).decode("utf-8")
        parts = raw.split("|", 1)
        if len(parts) != 2:
            raise ValueError("Malformed cursor payload")
        created_at = datetime.fromisoformat(parts[0])
        item_id = int(parts[1])
        return created_at, item_id
    except Exception as exc:
        raise ValidationError("Invalid pagination cursor") from exc
