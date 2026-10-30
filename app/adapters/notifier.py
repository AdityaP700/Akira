"""Notifier adapter interface and database-backed implementation."""

from typing import Any, Protocol

from sqlalchemy.orm import Session

from app.repositories.notifications import create_notification


class Notifier(Protocol):
    """Protocol for sending or persisting notifications within use-case transactions."""

    def notify(
        self,
        session: Session,
        user_id: int,
        event_type: str,
        title: str,
        message: str,
        group_id: int | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        """Record or send notification within the active database transaction."""
        ...


class DbNotifier:
    """Database-backed notification adapter persisting events to the notifications table."""

    def notify(
        self,
        session: Session,
        user_id: int,
        event_type: str,
        title: str,
        message: str,
        group_id: int | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        create_notification(
            session=session,
            user_id=user_id,
            event_type=event_type,
            title=title,
            message=message,
            group_id=group_id,
            data=data,
        )
