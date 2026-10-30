"""Repository for Group and GroupMember persistence."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.repositories.models import Group, GroupMember


def lock_for_update(session: Session, group_id: int) -> Group | None:
    """Lock and retrieve a group row using SELECT ... FOR UPDATE."""
    stmt = select(Group).where(Group.id == group_id).with_for_update()
    return session.scalar(stmt)


def get_by_id(session: Session, group_id: int) -> Group | None:
    """Retrieve a group by internal integer ID."""
    return session.get(Group, group_id)


def get_by_public_id(session: Session, public_id: str) -> Group | None:
    """Retrieve a group by public opaque ID."""
    stmt = select(Group).where(Group.public_id == public_id)
    return session.scalar(stmt)


def create(session: Session, name: str) -> Group:
    """Create a new group."""
    group = Group(name=name)
    session.add(group)
    session.flush()
    return group


def add_member(session: Session, group_id: int, user_id: int) -> GroupMember:
    """Add a user to a group."""
    member = GroupMember(group_id=group_id, user_id=user_id)
    session.add(member)
    session.flush()
    return member


def get_members(session: Session, group_id: int) -> list[GroupMember]:
    """List all members of a group."""
    stmt = select(GroupMember).where(GroupMember.group_id == group_id)
    return list(session.scalars(stmt).all())


def is_member(session: Session, group_id: int, user_id: int) -> bool:
    """Check if a user is a member of a group."""
    stmt = select(GroupMember).where(
        GroupMember.group_id == group_id, GroupMember.user_id == user_id
    )
    return session.scalar(stmt) is not None
