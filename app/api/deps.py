from collections.abc import Generator

from sqlalchemy.orm import Session

from app.core.db import get_session


def get_db() -> Generator[Session, None, None]:
    """Dependency that provides a transactional database session."""
    yield from get_session()


def get_actor() -> str | None:
    """Stub actor dependency for baseline; replaced by Bearer token authentication in A1."""
    return None
