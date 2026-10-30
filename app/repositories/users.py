"""Repository for User persistence."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.repositories.models import User


def create(session: Session, name: str) -> User:
    """Create a new user."""
    user = User(name=name)
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


def list_all(session: Session) -> list[User]:
    """List all users ordered by creation date."""
    stmt = select(User).order_by(User.id.asc())
    return list(session.scalars(stmt).all())
