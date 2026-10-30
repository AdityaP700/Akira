from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.adapters.keys import EnvKeyProvider, KeyProvider
from app.adapters.notifier import DbNotifier, Notifier
from app.adapters.payment_provider import MockPaymentProvider, PaymentProvider
from app.core.db import get_session
from app.core.errors import UnauthenticatedError
from app.repositories.models import User
from app.security.auth import authenticate_token

bearer_scheme = HTTPBearer(auto_error=False)

# Adapter singletons
_payment_provider = MockPaymentProvider()
_key_provider = EnvKeyProvider()
_notifier = DbNotifier()


def get_db() -> Generator[Session, None, None]:
    """Dependency that provides a transactional database session."""
    yield from get_session()


def get_payment_provider() -> PaymentProvider:
    """Dependency providing the PaymentProvider adapter."""
    return _payment_provider


def get_key_provider() -> KeyProvider:
    """Dependency providing the KeyProvider adapter."""
    return _key_provider


def get_notifier() -> Notifier:
    """Dependency providing the Notifier adapter."""
    return _notifier


def get_actor(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[Session, Depends(get_db)],
) -> User:
    """Extract and authenticate the Bearer token, returning the authenticated User actor."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise UnauthenticatedError(
            message="Authentication required: missing or invalid Bearer token"
        )

    token = credentials.credentials.strip()
    if not token:
        raise UnauthenticatedError(message="Bearer token cannot be empty")

    user = authenticate_token(session, token)
    if user is None:
        raise UnauthenticatedError(message="Invalid or revoked authentication token")

    request.state.actor_public_id = user.public_id
    request.state.actor = user

    # Detach user so its loaded attributes don't expire, and end the read transaction
    # so the service layer can begin its own use-case transaction with `with session.begin():`.
    session.expunge(user)
    session.rollback()

    return user
