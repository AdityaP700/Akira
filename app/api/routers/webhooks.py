"""Router for payment provider webhooks."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.adapters.keys import KeyProvider
from app.adapters.notifier import Notifier
from app.api.deps import get_db, get_key_provider, get_notifier
from app.services import settlements as settlements_service

router = APIRouter(tags=["webhooks"])


@router.post(
    "/webhooks/mock-provider",
    status_code=status.HTTP_200_OK,
    summary="Receive signed webhook callback from mock payment provider",
    description=(
        "Processes signed HMAC-SHA256 callbacks with timestamp verification, "
        "event deduplication, and forward-only settlement state transitions."
    ),
)
async def mock_provider_webhook(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    key_provider: Annotated[KeyProvider, Depends(get_key_provider)],
    notifier: Annotated[Notifier, Depends(get_notifier)],
    x_provider_signature: Annotated[str | None, Header(alias="X-Provider-Signature")] = None,
) -> Any:
    raw_body = await request.body()
    data, code = settlements_service.process_provider_webhook(
        session=db,
        raw_body=raw_body,
        signature_header=x_provider_signature,
        key_provider=key_provider,
        notifier=notifier,
    )
    return JSONResponse(status_code=code, content=data)
