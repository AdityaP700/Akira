"""Service layer for Notifications use cases."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.core.pagination import decode_cursor, encode_cursor
from app.repositories import notifications as notif_repo
from app.repositories.models import Group


def list_user_notifications(
    session: Session,
    user_id: int,
    unread_only: bool = False,
    cursor: str | None = None,
    limit: int = 20,
) -> tuple[list[dict[str, Any]], str | None]:
    """List notifications for the authenticated user."""
    cursor_id: int | None = None
    if cursor:
        _, cursor_id = decode_cursor(cursor)

    with session.begin():
        # Fetch limit + 1 to check if there is a next page
        raw_items = notif_repo.list_by_user(
            session=session,
            user_id=user_id,
            unread_only=unread_only,
            cursor=cursor_id,
            limit=limit + 1,
        )

        has_more = len(raw_items) > limit
        items = raw_items[:limit]

        # Resolve group public ids
        group_ids = {n.group_id for n in items if n.group_id is not None}
        group_map: dict[int, str] = {}
        if group_ids:
            groups = list(session.scalars(select(Group).where(Group.id.in_(group_ids))).all())
            group_map = {g.id: g.public_id for g in groups}

        out = [
            {
                "id": n.public_id,
                "event_type": n.event_type,
                "title": n.title,
                "message": n.message,
                "group_id": group_map.get(n.group_id) if n.group_id else None,
                "data": n.data,
                "read_at": n.read_at,
                "created_at": n.created_at,
            }
            for n in items
        ]

        next_cursor = None
        if has_more and items:
            last = items[-1]
            next_cursor = encode_cursor(last.created_at, last.id)

        return out, next_cursor


def mark_notification_read(
    session: Session, user_id: int, notification_public_id: str
) -> dict[str, Any]:
    """Mark a specific notification as read."""
    with session.begin():
        notif = notif_repo.mark_as_read(
            session=session, user_id=user_id, public_id=notification_public_id
        )
        if notif is None:
            raise NotFoundError("Notification not found")

        group_public_id = None
        if notif.group_id:
            grp = session.get(Group, notif.group_id)
            if grp:
                group_public_id = grp.public_id

        return {
            "id": notif.public_id,
            "event_type": notif.event_type,
            "title": notif.title,
            "message": notif.message,
            "group_id": group_public_id,
            "data": notif.data,
            "read_at": notif.read_at,
            "created_at": notif.created_at,
        }
