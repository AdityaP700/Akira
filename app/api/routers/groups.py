"""Router for group and group membership endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_actor, get_db
from app.api.schemas.groups import GroupIn, GroupMemberOut, GroupOut, MemberIn
from app.services import groups as groups_service

router = APIRouter(prefix="/groups", tags=["groups"])


@router.post(
    "",
    response_model=GroupOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new group",
    description="Create a new expense group. Returns opaque public ID (grp_...).",
)
def create_group(
    payload: GroupIn,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[str | None, Depends(get_actor)] = None,
) -> GroupOut:
    group = groups_service.create_group(db, payload.name)
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
    description="Add an existing user to an expense sharing group.",
)
def add_member(
    group_id: str,
    payload: MemberIn,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[str | None, Depends(get_actor)] = None,
) -> GroupMemberOut:
    member, user_name = groups_service.add_member(
        db, group_public_id=group_id, user_public_id=payload.user_id
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
    description="Retrieve all members of a specific group.",
)
def list_members(
    group_id: str,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[str | None, Depends(get_actor)] = None,
) -> list[GroupMemberOut]:
    members_with_names = groups_service.list_members(db, group_public_id=group_id)
    return [
        GroupMemberOut(
            group_id=group_id,
            user_id=user_public_id,
            name=user_name,
            joined_at=m.joined_at,
        )
        for m, user_name, user_public_id in members_with_names
    ]
