"""Repository for idempotency key storage and retrieval."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.repositories.models import IdempotencyKey


def get(session: Session, scope: str, key: str) -> IdempotencyKey | None:
    """Retrieve an idempotency record by scope and key."""
    stmt = select(IdempotencyKey).where(IdempotencyKey.scope == scope, IdempotencyKey.key == key)
    return session.scalar(stmt)


def save(
    session: Session,
    scope: str,
    key: str,
    request_fingerprint: str,
    response_status: int | None = None,
    response_body: Any | None = None,
) -> IdempotencyKey:
    """Save or update an idempotency record."""
    record = session.get(IdempotencyKey, (scope, key))
    if record is None:
        record = IdempotencyKey(
            scope=scope,
            key=key,
            request_fingerprint=request_fingerprint,
            response_status=response_status,
            response_body=response_body,
        )
        session.add(record)
    else:
        record.request_fingerprint = request_fingerprint
        record.response_status = response_status
        record.response_body = response_body

    session.flush()
    return record
