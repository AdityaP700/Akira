"""Router for audit verification of ledger hash chains."""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.adapters.keys import KeyProvider
from app.api.deps import get_actor, get_db, get_key_provider
from app.api.schemas.audit import AuditVerifyOut
from app.repositories.models import User
from app.services import audit as audit_service

router = APIRouter(prefix="/groups/{group_id}/audit", tags=["audit"])


@router.get(
    "/verify",
    response_model=AuditVerifyOut,
    status_code=status.HTTP_200_OK,
    summary="Verify group ledger cryptographic integrity",
    description=(
        "Recomputes the HMAC-SHA256 hash chain, checks sequence continuity, "
        "and cross-checks payloads."
    ),
)
def verify_audit(
    group_id: str,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[User, Depends(get_actor)],
    key_provider: Annotated[KeyProvider, Depends(get_key_provider)],
) -> AuditVerifyOut:
    result = audit_service.verify_group_ledger(
        session=db,
        group_public_id=group_id,
        actor=actor,
        key_provider=key_provider,
    )
    return AuditVerifyOut(
        valid=result["valid"],
        entries=result.get("entries"),
        head=result.get("head"),
        broken_at=result.get("broken_at"),
        reason=result.get("reason"),
    )
