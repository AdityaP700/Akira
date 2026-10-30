"""Router for expense management endpoints."""

import json
import re
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Request, status
from sqlalchemy.orm import Session

from app.adapters.keys import KeyProvider
from app.api.deps import get_actor, get_db, get_key_provider
from app.api.schemas.expenses import ExpenseIn, ExpenseListOut, ExpenseOut
from app.core.errors import ValidationError
from app.repositories.models import User
from app.services import expenses as expenses_service

router = APIRouter(tags=["expenses"])

IDEMPOTENCY_KEY_REGEX = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _validate_idempotency_key(key: str | None) -> None:
    if key is not None and not IDEMPOTENCY_KEY_REGEX.fullmatch(key):
        raise ValidationError("Invalid Idempotency-Key header format")


@router.post(
    "/groups/{group_id}/expenses",
    response_model=ExpenseOut,
    status_code=status.HTTP_201_CREATED,
    summary="Record a shared expense in a group",
    description="Atomic expense creation with shares, append-only ledger, and idempotency.",
)
def create_group_expense(
    group_id: str,
    payload: ExpenseIn,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[User, Depends(get_actor)],
    key_provider: Annotated[KeyProvider, Depends(get_key_provider)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> Any:
    _validate_idempotency_key(idempotency_key)
    canonical_body = json.dumps(payload.model_dump(), sort_keys=True, separators=(",", ":"))
    data, _ = expenses_service.create_expense(
        session=db,
        group_public_id=group_id,
        payload=payload,
        actor=actor,
        idempotency_key=idempotency_key,
        http_method=request.method,
        http_path=f"/groups/{group_id}/expenses",
        canonical_body=canonical_body,
        key_provider=key_provider,
    )
    return data


@router.post(
    "/expenses",
    response_model=ExpenseOut,
    status_code=status.HTTP_201_CREATED,
    summary="Record a shared expense (brief-compatible alias)",
    description="Brief-compatible alias requiring group_id in body.",
)
def create_expense_alias(
    payload: ExpenseIn,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[User, Depends(get_actor)],
    key_provider: Annotated[KeyProvider, Depends(get_key_provider)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> Any:
    _validate_idempotency_key(idempotency_key)
    if not payload.group_id:
        raise ValidationError("group_id is required in request body for /expenses")

    canonical_body = json.dumps(payload.model_dump(), sort_keys=True, separators=(",", ":"))
    data, _ = expenses_service.create_expense(
        session=db,
        group_public_id=payload.group_id,
        payload=payload,
        actor=actor,
        idempotency_key=idempotency_key,
        http_method=request.method,
        http_path="/expenses",
        canonical_body=canonical_body,
        key_provider=key_provider,
    )
    return data


@router.get(
    "/groups/{group_id}/expenses",
    response_model=ExpenseListOut,
    status_code=status.HTTP_200_OK,
    summary="List expenses for a group",
    description="Keyset paginated list of expenses ordered newest first.",
)
def list_group_expenses(
    group_id: str,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[User, Depends(get_actor)],
    limit: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 20,
    cursor: Annotated[str | None, Query(description="Keyset pagination cursor")] = None,
) -> ExpenseListOut:
    items, next_cursor = expenses_service.list_expenses(
        session=db,
        group_public_id=group_id,
        actor=actor,
        limit=limit,
        cursor=cursor,
    )
    return ExpenseListOut(items=items, next_cursor=next_cursor)  # type: ignore[arg-type]
