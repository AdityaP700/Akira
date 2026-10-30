"""Repository for Settlement persistence."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.repositories.models import Settlement


def create(
    session: Session,
    group_id: int,
    from_user: int,
    to_user: int,
    amount_paise: int,
    status: str = "CONFIRMED",
    method: str = "OTHER",
) -> Settlement:
    """Create a new settlement record."""
    settlement = Settlement(
        group_id=group_id,
        from_user=from_user,
        to_user=to_user,
        amount_paise=amount_paise,
        status=status,
        method=method,
    )
    session.add(settlement)
    session.flush()
    return settlement


def list_by_group(session: Session, group_id: int) -> list[Settlement]:
    """List all settlements for a group ordered newest first."""
    stmt = (
        select(Settlement)
        .where(Settlement.group_id == group_id)
        .order_by(Settlement.created_at.desc(), Settlement.id.desc())
    )
    return list(session.scalars(stmt).all())
