import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_db

logger = logging.getLogger("app.api.health")

router = APIRouter(tags=["health"])


@router.get("/health", response_model=None)
def health_check(session: Annotated[Session, Depends(get_db)]) -> Response:
    """Run SELECT 1 with a 2-second timeout. Return 200 ok or 503 degraded."""
    try:
        session.execute(
            text("SELECT 1"),
            execution_options={"timeout": 2.0},
        )
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"status": "ok", "db": "ok"},
        )
    except Exception as exc:
        logger.warning("Database health check failed: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "degraded", "db": "down"},
        )
