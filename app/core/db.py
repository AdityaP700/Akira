from collections.abc import Generator
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.core.config import settings

Base = declarative_base()


def get_connect_args(url: str) -> dict[str, Any]:
    """Configure driver-specific connection arguments (e.g., 5s statement timeout)."""
    if "postgresql" in url:
        return {
            "options": "-c statement_timeout=5000",
            "connect_timeout": 5,
        }
    if "sqlite" in url:
        return {"check_same_thread": False}
    return {}


def create_app_engine(url: str = settings.DATABASE_URL) -> Engine:
    connect_args = get_connect_args(url)
    engine_kwargs: dict[str, Any] = {
        "pool_pre_ping": True,
        "connect_args": connect_args,
    }
    if "sqlite" not in url:
        engine_kwargs["pool_timeout"] = 5

    return create_engine(url, **engine_kwargs)


engine = create_app_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_session() -> Generator[Session, None, None]:
    """Yield a database session and ensure it is properly closed."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
