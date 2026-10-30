"""Authorization guards and object-level permission checks (OWASP API1 / API5)."""

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.repositories import groups as groups_repo
from app.repositories.models import Group, User


def require_member(session: Session, group_public_id: str, actor: User) -> Group:
    """Validate that actor is a member of the group identified by group_public_id.

    Returns the Group instance on success.
    Raises NotFoundError (HTTP 404) if group does not exist OR if actor is not a member,
    ensuring error responses are identical to prevent ID enumeration (OWASP API1 BOLA).
    """
    group = groups_repo.get_by_public_id(session, group_public_id)
    if group is None:
        raise NotFoundError(f"Group '{group_public_id}' not found")

    if not groups_repo.is_member(session, group.id, actor.id):
        raise NotFoundError(f"Group '{group_public_id}' not found")

    return group


def require_member_and_lock(session: Session, group_public_id: str, actor: User) -> Group:
    """Acquire an exclusive row lock on the group and validate that actor is a member.

    Executes SELECT ... FOR UPDATE on the group row.
    Raises NotFoundError (HTTP 404) if group does not exist OR if actor is not a member.
    """
    group = groups_repo.lock_for_update_by_public_id(session, group_public_id)
    if group is None:
        raise NotFoundError(f"Group '{group_public_id}' not found")

    if not groups_repo.is_member(session, group.id, actor.id):
        raise NotFoundError(f"Group '{group_public_id}' not found")

    return group
