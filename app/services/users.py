"""Service layer for User operations."""

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core.pagination import decode_cursor, encode_cursor
from app.repositories import users as users_repo
from app.repositories.models import GroupMember, User
from app.security.auth import generate_api_token, hash_token


def create_user(session: Session, name: str) -> tuple[User, str]:
    """Create a new user with a generated bearer token within a transaction."""
    raw_token = generate_api_token()
    token_h = hash_token(raw_token)
    with session.begin():
        user = users_repo.create(session, name=name, token_hash=token_h)
    return user, raw_token


def rotate_user_token(session: Session, user_id: int) -> str:
    """Generate a new bearer token and replace the old token hash in one atomic transaction."""
    new_raw_token = generate_api_token()
    new_token_h = hash_token(new_raw_token)
    with session.begin():
        users_repo.update_token_hash(session, user_id, new_token_h)
    return new_raw_token


def list_users(
    session: Session,
    actor: User,
    limit: int = 20,
    cursor: str | None = None,
) -> tuple[list[User], str | None]:
    """List users who share at least one group with actor, using keyset pagination."""
    with session.begin():
        actor_groups = select(GroupMember.group_id).where(GroupMember.user_id == actor.id)
        shared_user_ids = select(GroupMember.user_id).where(GroupMember.group_id.in_(actor_groups))

        stmt = select(User).where((User.id == actor.id) | User.id.in_(shared_user_ids))

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
