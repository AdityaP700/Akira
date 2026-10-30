"""Service layer for User operations."""

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core.pagination import decode_cursor, encode_cursor
from app.repositories import users as users_repo
from app.repositories.models import User


def create_user(session: Session, name: str) -> User:
    """Create a new user within a transaction."""
    with session.begin():
        return users_repo.create(session, name)


def list_users(
    session: Session,
    limit: int = 20,
    cursor: str | None = None,
) -> tuple[list[User], str | None]:
    """List users using keyset pagination."""
    with session.begin():
        stmt = select(User)
        if cursor is not None:
            created_at_bound, id_bound = decode_cursor(cursor)
            stmt = stmt.where(
                or_(
                    User.created_at < created_at_bound,
                    and_(
                        User.created_at == created_at_bound,
                        User.id < id_bound,
                    ),
                )
            )

        stmt = stmt.order_by(User.created_at.desc(), User.id.desc()).limit(limit + 1)
        items = list(session.scalars(stmt).all())

        if len(items) > limit:
            paginated = items[:limit]
            next_cursor = encode_cursor(paginated[-1].created_at, paginated[-1].id)
            return paginated, next_cursor

        return items, None
