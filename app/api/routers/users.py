"""Router for user management endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.adapters.keys import KeyProvider
from app.api.deps import get_actor, get_db, get_key_provider
from app.api.schemas.users import (
    TokenRotateOut,
    UserIn,
    UserListOut,
    UserOut,
    UserRegistrationOut,
    UserVpaIn,
    UserVpaOut,
)
from app.core.config import settings
from app.repositories.models import User
from app.security.ratelimit import limiter
from app.services import users as users_service

router = APIRouter(prefix="/users", tags=["users"])


@router.post(
    "",
    response_model=UserRegistrationOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new user",
    description="Register a new user. Returns opaque public ID and initial API bearer token.",
)
@limiter.limit(lambda: settings.RATE_LIMIT_USER_REGISTRATION)
@limiter.limit(
    lambda: settings.RATE_LIMIT_DEMO_GLOBAL_REGISTRATION,
    key_func=lambda *args, **kwargs: "global:demo_user_registration",
    exempt_when=lambda *args, **kwargs: settings.APP_ENV != "demo",
)
def create_user(
    request: Request,
    payload: UserIn,
    db: Annotated[Session, Depends(get_db)],
) -> UserRegistrationOut:
    user, token = users_service.create_user(db, payload.name)
    return UserRegistrationOut(
        user=UserOut(
            id=user.public_id,
            name=user.name,
            created_at=user.created_at,
        ),
        api_token=token,
    )


@router.post(
    "/me/token/rotate",
    response_model=TokenRotateOut,
    status_code=status.HTTP_200_OK,
    summary="Rotate caller's API bearer token",
    description="Invalidates the current bearer token and returns a new one.",
)
def rotate_token(
    actor: Annotated[User, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
) -> TokenRotateOut:
    new_token = users_service.rotate_user_token(db, actor.id)
    return TokenRotateOut(api_token=new_token)


@router.get(
    "/me",
    response_model=UserOut,
    status_code=status.HTTP_200_OK,
    summary="Get current user profile",
    description="Returns authenticated user details including masked VPA if configured.",
)
def get_current_user(
    actor: Annotated[User, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    key_provider: Annotated[KeyProvider, Depends(get_key_provider)],
) -> UserOut:
    masked_vpa = users_service.get_masked_user_vpa(db, actor.id, actor.public_id, key_provider)
    return UserOut(
        id=actor.public_id,
        name=actor.name,
        created_at=actor.created_at,
        vpa_masked=masked_vpa,
    )


@router.put(
    "/me/vpa",
    response_model=UserVpaOut,
    status_code=status.HTTP_200_OK,
    summary="Set or update caller's UPI VPA",
    description=(
        "Encrypts VPA at application layer with AES-256-GCM and stores blind index for lookup."
    ),
)
def set_vpa(
    payload: UserVpaIn,
    actor: Annotated[User, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    key_provider: Annotated[KeyProvider, Depends(get_key_provider)],
) -> UserVpaOut:
    masked = users_service.set_user_vpa(db, actor, payload.vpa, key_provider)
    return UserVpaOut(vpa_masked=masked)


@router.get(
    "",
    response_model=UserListOut,
    status_code=status.HTTP_200_OK,
    summary="List users",
    description="Retrieve users who share at least one group with the authenticated caller.",
)
def list_users(
    actor: Annotated[User, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 20,
    cursor: Annotated[str | None, Query(description="Keyset pagination cursor")] = None,
) -> UserListOut:
    items, next_cursor = users_service.list_users(db, actor=actor, limit=limit, cursor=cursor)
    return UserListOut(
        items=[
            UserOut(
                id=u.public_id,
                name=u.name,
                created_at=u.created_at,
            )
            for u in items
        ],
        next_cursor=next_cursor,
    )
