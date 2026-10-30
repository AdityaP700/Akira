"""Service layer for Group and Membership operations."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.repositories import groups as groups_repo
from app.repositories import users as users_repo
from app.repositories.models import Group, GroupMember, User
from app.security.guards import require_member


def create_group(session: Session, name: str, creator: User) -> Group:
    """Create a new group within a transaction and make the creator its first member."""
    with session.begin():
        group = groups_repo.create(session, name)
        groups_repo.add_member(session, group.id, creator.id)
        return group


def add_member(
    session: Session,
    group_public_id: str,
    user_public_id: str,
    actor: User,
) -> tuple[GroupMember, str]:
    """Add a user to a group, returning the member record and user display name.

    Only existing group members can add new members.
    Raises:
        NotFoundError: If group does not exist or caller is not a member (OWASP API1).
        NotFoundError: If user to add does not exist.
        ConflictError: If user is already a member.
    """
    with session.begin():
        group = require_member(session, group_public_id, actor)

        user = users_repo.get_by_public_id(session, user_public_id)
        if user is None:
            raise NotFoundError(f"User '{user_public_id}' not found")

        if groups_repo.is_member(session, group.id, user.id):
            raise ConflictError(
                code="ALREADY_MEMBER",
                message=f"User '{user_public_id}' is already a member of group '{group_public_id}'",
            )

        member = groups_repo.add_member(session, group.id, user.id)
        return member, user.name


def list_members(
    session: Session,
    group_public_id: str,
    actor: User,
) -> list[tuple[GroupMember, str, str]]:
    """List all members of a group with user display names and public IDs.

    Raises:
        NotFoundError: If group does not exist or caller is not a member (OWASP API1).
    """
    with session.begin():
        group = require_member(session, group_public_id, actor)

        stmt = (
            select(GroupMember, User.name, User.public_id)
            .join(User, GroupMember.user_id == User.id)
            .where(GroupMember.group_id == group.id)
            .order_by(GroupMember.joined_at.asc())
        )
        results = session.execute(stmt).all()
        return [(row[0], row[1], row[2]) for row in results]
