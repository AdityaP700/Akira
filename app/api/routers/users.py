"""Router for user management endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.schemas.users import UserIn, UserListOut, UserOut
from app.services import users as users_service

router = APIRouter(prefix="/users", tags=["users"])


@router.post(
    "",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new user",
    description="Register a new user by display name. Returns opaque public ID (usr_...).",
)
def create_user(
    payload: UserIn,
    db: Annotated[Session, Depends(get_db)],
) -> UserOut:
    user = users_service.create_user(db, payload.name)
    return UserOut(
        id=user.public_id,
        name=user.name,
        created_at=user.created_at,
    )


@router.get(
    "",
    response_model=UserListOut,
    status_code=status.HTTP_200_OK,
    summary="List users",
    description="Retrieve a paginated list of users using keyset cursor pagination.",
)
def list_users(
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 20,
    cursor: Annotated[str | None, Query(description="Keyset pagination cursor")] = None,
) -> UserListOut:
    items, next_cursor = users_service.list_users(db, limit=limit, cursor=cursor)
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
