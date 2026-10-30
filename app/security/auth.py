"""Authentication and token verification for Akira.

Design:
- Token format: 'est_' prefix + secrets.token_urlsafe(32) for secret scanning compatibility.
- DB stores SHA-256 hash only.
- Authentication compares token hash using hmac.compare_digest for constant-time comparison.
"""

import hashlib
import hmac
import secrets

from sqlalchemy.orm import Session

from app.repositories import users as users_repo
from app.repositories.models import User

TOKEN_PREFIX = "est_"  # noqa: S105


def generate_api_token() -> str:
    """Generate a high-entropy cryptographically secure API bearer token."""
    return f"{TOKEN_PREFIX}{secrets.token_urlsafe(32)}"


def hash_token(token: str) -> str:
    """Hash a bearer token using SHA-256."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_token(token: str, expected_hash: str) -> bool:
    """Verify a token against an expected SHA-256 hash using constant-time comparison."""
    computed_hash = hash_token(token)
    return hmac.compare_digest(computed_hash, expected_hash)


def authenticate_token(session: Session, token: str) -> User | None:
    """Authenticate a raw bearer token against stored user token hashes."""
    if not token or not isinstance(token, str):
        return None

    computed_hash = hash_token(token)
    user = users_repo.get_by_token_hash(session, computed_hash)
    if user is None or user.token_hash is None:
        return None

    if not hmac.compare_digest(user.token_hash, computed_hash):
        return None

    return user
