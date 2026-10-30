"""Repository for Notifications persistence."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.repositories.models import Notification


def create_notification(
    session: Session,
    user_id: int,
    event_type: str,
    title: str,
    message: str,
    group_id: int | None = None,
    data: dict[str, Any] | None = None,
) -> Notification:
    """Create a new user notification."""
    notif = Notification(
        user_id=user_id,
        event_type=event_type,
        group_id=group_id,
        title=title,
        message=message,
        data=data,
    )
    session.add(notif)
    session.flush()
    return notif


def list_by_user(
    session: Session,
    user_id: int,
    unread_only: bool = False,
    cursor: int | None = None,
    limit: int = 20,
) -> list[Notification]:
    """List notifications for a user, newest first, with unread filter and keyset pagination."""
    stmt = select(Notification).where(Notification.user_id == user_id)
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))

    if cursor is not None:
        stmt = stmt.where(Notification.id < cursor)

    stmt = stmt.order_by(Notification.id.desc()).limit(limit)
    return list(session.scalars(stmt).all())


def mark_as_read(session: Session, user_id: int, public_id: str) -> Notification | None:
    """Mark a notification as read."""
    stmt = select(Notification).where(
        Notification.user_id == user_id, Notification.public_id == public_id
    )
    notif = session.scalar(stmt)
    if notif and notif.read_at is None:
        notif.read_at = datetime.now(UTC)
        session.flush()
    return notif
