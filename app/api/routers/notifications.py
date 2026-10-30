"""Router for User notification endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_actor, get_db
from app.api.schemas.notifications import NotificationListOut, NotificationOut
from app.repositories.models import User
from app.services import notifications as notif_service

router = APIRouter(tags=["notifications"])


@router.get(
    "/users/me/notifications",
    response_model=NotificationListOut,
    status_code=status.HTTP_200_OK,
    summary="List notifications for authenticated user",
    description="Retrieve chronological notifications with unread filter and pagination.",
)
def get_user_notifications(
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[User, Depends(get_actor)],
    unread: Annotated[bool, Query(description="Filter unread notifications only")] = False,
    limit: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 20,
    cursor: Annotated[str | None, Query(description="Keyset pagination cursor")] = None,
) -> NotificationListOut:
    items, next_cursor = notif_service.list_user_notifications(
        session=db,
        user_id=actor.id,
        unread_only=unread,
        cursor=cursor,
        limit=limit,
    )
    return NotificationListOut(items=items, next_cursor=next_cursor)  # type: ignore[arg-type]


@router.post(
    "/users/me/notifications/{notification_id}/read",
    response_model=NotificationOut,
    status_code=status.HTTP_200_OK,
    summary="Mark a notification as read",
    description="Update notification read status for the authenticated user.",
)
def mark_notification_read(
    notification_id: str,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[User, Depends(get_actor)],
) -> NotificationOut:
    data = notif_service.mark_notification_read(
        session=db,
        user_id=actor.id,
        notification_public_id=notification_id,
    )
    return NotificationOut(**data)
