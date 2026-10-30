"""Router for settlement repayment endpoints."""

import json
import re
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_actor, get_db
from app.api.schemas.settlements import SettlementIn, SettlementListOut, SettlementOut
from app.core.errors import ValidationError
from app.repositories.models import User
from app.services import settlements as settlements_service

router = APIRouter(tags=["settlements"])

IDEMPOTENCY_KEY_REGEX = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _validate_idempotency_key(key: str | None) -> None:
    if key is not None and not IDEMPOTENCY_KEY_REGEX.fullmatch(key):
        raise ValidationError("Invalid Idempotency-Key header format")


@router.post(
    "/groups/{group_id}/settlements",
    response_model=SettlementOut,
    status_code=status.HTTP_201_CREATED,
    summary="Record a settlement repayment",
    description=(
        "Record repayment between group members with overpayment check and ledger entry. "
        "Requires caller to be a member."
    ),
)
def create_settlement(
    group_id: str,
    payload: SettlementIn,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[User, Depends(get_actor)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> Any:
    _validate_idempotency_key(idempotency_key)
    canonical_body = json.dumps(payload.model_dump(), sort_keys=True, separators=(",", ":"))
    data, _ = settlements_service.record_settlement(
        session=db,
        group_public_id=group_id,
        payload=payload,
        actor=actor,
        idempotency_key=idempotency_key,
        http_method=request.method,
        http_path=f"/groups/{group_id}/settlements",
        canonical_body=canonical_body,
    )
    return data


@router.get(
    "/groups/{group_id}/settlements",
    response_model=SettlementListOut,
    status_code=status.HTTP_200_OK,
    summary="List settlements for a group",
    description=(
        "Keyset paginated list of recorded settlements ordered newest first. "
        "Requires caller to be a member."
    ),
)
def list_settlements(
    group_id: str,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[User, Depends(get_actor)],
    limit: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 20,
    cursor: Annotated[str | None, Query(description="Keyset pagination cursor")] = None,
) -> SettlementListOut:
    items, next_cursor = settlements_service.list_settlements(
        session=db,
        group_public_id=group_id,
        actor=actor,
        limit=limit,
        cursor=cursor,
    )
    return SettlementListOut(items=items, next_cursor=next_cursor)  # type: ignore[arg-type]
