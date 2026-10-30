"""Router for group and group membership endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_actor, get_db
from app.api.schemas.groups import GroupIn, GroupMemberOut, GroupOut, MemberIn
from app.repositories.models import User
from app.services import groups as groups_service

router = APIRouter(prefix="/groups", tags=["groups"])


@router.post(
    "",
    response_model=GroupOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new group",
    description="Create a group. Creator is automatically added as its first member.",
)
def create_group(
    payload: GroupIn,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[User, Depends(get_actor)],
) -> GroupOut:
    group = groups_service.create_group(db, payload.name, creator=actor)
    return GroupOut(
        id=group.public_id,
        name=group.name,
        created_at=group.created_at,
    )


@router.post(
    "/{group_id}/members",
    response_model=GroupMemberOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add a member to a group",
    description="Add an existing user to group. Requires caller to be an active member.",
)
def add_member(
    group_id: str,
    payload: MemberIn,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[User, Depends(get_actor)],
) -> GroupMemberOut:
    member, user_name = groups_service.add_member(
        db, group_public_id=group_id, user_public_id=payload.user_id, actor=actor
    )
    return GroupMemberOut(
        group_id=group_id,
        user_id=payload.user_id,
        name=user_name,
        joined_at=member.joined_at,
    )


@router.get(
    "/{group_id}/members",
    response_model=list[GroupMemberOut],
    status_code=status.HTTP_200_OK,
    summary="List group members",
    description="Retrieve all members of a specific group. Requires caller to be an active member.",
)
def list_members(
    group_id: str,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[User, Depends(get_actor)],
) -> list[GroupMemberOut]:
    members_with_names = groups_service.list_members(db, group_public_id=group_id, actor=actor)
    return [
        GroupMemberOut(
            group_id=group_id,
            user_id=user_public_id,
            name=user_name,
            joined_at=m.joined_at,
        )
        for m, user_name, user_public_id in members_with_names
    ]
