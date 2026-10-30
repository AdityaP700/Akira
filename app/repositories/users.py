"""Repository for User persistence."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.repositories.models import GroupMember, User


def create(session: Session, name: str, token_hash: str | None = None) -> User:
    """Create a new user."""
    user = User(name=name, token_hash=token_hash)
    session.add(user)
    session.flush()
    return user


def get_by_id(session: Session, user_id: int) -> User | None:
    """Retrieve a user by internal integer ID."""
    return session.get(User, user_id)


def get_by_public_id(session: Session, public_id: str) -> User | None:
    """Retrieve a user by public opaque ID."""
    stmt = select(User).where(User.public_id == public_id)
    return session.scalar(stmt)


def get_by_token_hash(session: Session, token_hash: str) -> User | None:
    """Retrieve a user by SHA-256 token hash."""
    stmt = select(User).where(User.token_hash == token_hash)
    return session.scalar(stmt)


def update_token_hash(session: Session, user_id: int, new_token_hash: str) -> None:
    """Update a user's token hash."""
    user = session.get(User, user_id)
    if user:
        user.token_hash = new_token_hash
        session.flush()


def list_shared_users(session: Session, user_id: int) -> list[User]:
    """List users who share at least one group with user_id, including user_id."""
    actor_groups = select(GroupMember.group_id).where(GroupMember.user_id == user_id)
    shared_user_ids = select(GroupMember.user_id).where(GroupMember.group_id.in_(actor_groups))
    stmt = (
        select(User)
        .where((User.id == user_id) | User.id.in_(shared_user_ids))
        .order_by(User.id.asc())
    )
    return list(session.scalars(stmt).all())


def list_all(session: Session) -> list[User]:
    """List all users ordered by creation date."""
    stmt = select(User).order_by(User.id.asc())
    return list(session.scalars(stmt).all())
