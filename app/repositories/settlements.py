"""Repository for Settlement persistence."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.ids import new_reference_id
from app.repositories.models import ProviderEvent, Settlement


def create(
    session: Session,
    group_id: int,
    from_user: int,
    to_user: int,
    amount_paise: int,
    status: str = "CONFIRMED",
    method: str = "OTHER",
    created_by: int | None = None,
    reference: str | None = None,
    provider_intent: dict[str, Any] | None = None,
) -> Settlement:
    """Create a new settlement record."""
    if reference is None:
        reference = new_reference_id()

    settlement = Settlement(
        group_id=group_id,
        from_user=from_user,
        to_user=to_user,
        amount_paise=amount_paise,
        status=status,
        method=method,
        created_by=created_by,
        reference=reference,
        provider_intent=provider_intent,
    )
    session.add(settlement)
    session.flush()
    return settlement


def get_by_id(session: Session, settlement_id: int) -> Settlement | None:
    return session.get(Settlement, settlement_id)


def get_by_public_id(session: Session, public_id: str) -> Settlement | None:
    stmt = select(Settlement).where(Settlement.public_id == public_id)
    return session.scalar(stmt)


def get_by_reference(session: Session, reference: str) -> Settlement | None:
    stmt = select(Settlement).where(Settlement.reference == reference)
    return session.scalar(stmt)


def list_by_group(
    session: Session, group_id: int, cursor: int | None = None, limit: int = 20
) -> list[Settlement]:
    """List all settlements for a group ordered newest first."""
    stmt = select(Settlement).where(Settlement.group_id == group_id)
    if cursor is not None:
        stmt = stmt.where(Settlement.id < cursor)
    stmt = stmt.order_by(Settlement.id.desc()).limit(limit)
    return list(session.scalars(stmt).all())


def get_provider_event(session: Session, event_id: str) -> ProviderEvent | None:
    return session.get(ProviderEvent, event_id)


def record_provider_event(
    session: Session,
    event_id: str,
    reference: str,
    status: str,
    amount_paise: int,
) -> ProviderEvent:
    event = ProviderEvent(
        event_id=event_id,
        reference=reference,
        status=status,
        amount_paise=amount_paise,
    )
    session.add(event)
    session.flush()
    return event
