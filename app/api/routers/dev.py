"""Development and testing helper endpoints (disabled in production)."""

import json
import secrets
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.adapters.keys import KeyProvider
from app.adapters.notifier import Notifier
from app.api.deps import get_db, get_key_provider, get_notifier
from app.core.errors import NotFoundError
from app.domain.money import format_paise
from app.repositories import settlements as settlements_repo
from app.security.signatures import build_signature_header
from app.services import settlements as settlements_service

router = APIRouter(prefix="/dev", tags=["dev"])


@router.post(
    "/mock-provider/pay/{reference}",
    status_code=status.HTTP_200_OK,
    summary="Simulate payment provider callback for demo/testing",
    description="Constructs and signs a provider webhook callback with outcome=success|failed.",
)
def simulate_provider_payment(
    reference: str,
    db: Annotated[Session, Depends(get_db)],
    key_provider: Annotated[KeyProvider, Depends(get_key_provider)],
    notifier: Annotated[Notifier, Depends(get_notifier)],
    outcome: Annotated[Literal["success", "failed"], Query()] = "success",
) -> Any:
    settlement = settlements_repo.get_by_reference(db, reference)
    if settlement is None:
        raise NotFoundError(f"Settlement with reference '{reference}' not found")

    event_id = f"evt_{secrets.token_hex(12)}"
    status_str = "SUCCESS" if outcome.lower() == "success" else "FAILED"
    amount_str = format_paise(settlement.amount_paise)
    db.rollback()

    payload_dict = {
        "event_id": event_id,
        "reference": reference,
        "status": status_str,
        "amount": amount_str,
    }
    raw_body = json.dumps(payload_dict, separators=(",", ":")).encode("utf-8")

    kid, secret_hex = key_provider.get_current_webhook_key()
    signature_header = build_signature_header(kid, secret_hex, raw_body)

    data, code = settlements_service.process_provider_webhook(
        session=db,
        raw_body=raw_body,
        signature_header=signature_header,
        key_provider=key_provider,
        notifier=notifier,
    )
    return data
