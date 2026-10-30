"""Pydantic schemas for Notification requests and responses."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class NotificationOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    event_type: str
    title: str
    message: str
    group_id: str | None = None
    data: dict[str, Any] | None = None
    read_at: datetime | None = None
    created_at: datetime


class NotificationListOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[NotificationOut]
    next_cursor: str | None = None
