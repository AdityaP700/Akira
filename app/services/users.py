"""Service layer for User operations."""

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.adapters.keys import KeyProvider
from app.core.errors import ConflictError
from app.core.pagination import decode_cursor, encode_cursor
from app.repositories import users as users_repo
from app.repositories.models import GroupMember, User
from app.security.auth import generate_api_token, hash_token
from app.security.pii import compute_blind_index, decrypt_vpa, encrypt_vpa, mask_vpa


def create_user(session: Session, name: str) -> tuple[User, str]:
    """Create a new user with a generated bearer token within a transaction."""
    raw_token = generate_api_token()
    token_h = hash_token(raw_token)
    with session.begin():
        user = users_repo.create(session, name=name, token_hash=token_h)
    return user, raw_token


def rotate_user_token(session: Session, user_id: int) -> str:
    """Generate a new bearer token and replace the old token hash in one atomic transaction."""
    new_raw_token = generate_api_token()
    new_token_h = hash_token(new_raw_token)
    with session.begin():
        users_repo.update_token_hash(session, user_id, new_token_h)
    return new_raw_token


def list_users(
    session: Session,
    actor: User,
    limit: int = 20,
    cursor: str | None = None,
) -> tuple[list[User], str | None]:
    """List users who share at least one group with actor, using keyset pagination."""
    with session.begin():
        actor_groups = select(GroupMember.group_id).where(GroupMember.user_id == actor.id)
        shared_user_ids = select(GroupMember.user_id).where(GroupMember.group_id.in_(actor_groups))

        stmt = select(User).where((User.id == actor.id) | User.id.in_(shared_user_ids))

        if cursor is not None:
            created_at_bound, id_bound = decode_cursor(cursor)
            stmt = stmt.where(
                or_(
                    User.created_at < created_at_bound,
                    and_(
                        User.created_at == created_at_bound,
                        User.id < id_bound,
                    ),
                )
            )

        stmt = stmt.order_by(User.created_at.desc(), User.id.desc()).limit(limit + 1)
        items = list(session.scalars(stmt).all())

        if len(items) > limit:
            paginated = items[:limit]
            next_cursor = encode_cursor(paginated[-1].created_at, paginated[-1].id)
            return paginated, next_cursor

        return items, None


def set_user_vpa(
    session: Session,
    actor: User,
    vpa: str,
    key_provider: KeyProvider,
) -> str:
    """Set or update user's encrypted VPA and blind index."""
    kid, enc_hex, blind_hex = key_provider.get_current_pii_key()
    blind_key = bytes.fromhex(blind_hex)
    blind_index = compute_blind_index(blind_key, vpa)

    with session.begin():
        existing = users_repo.get_pii_by_blind_index(session, blind_index)
        if existing is not None and existing.user_id != actor.id:
            raise ConflictError(
                code="VPA_ALREADY_IN_USE",
                message="This VPA is already linked to another account",
            )

        enc_key = bytes.fromhex(enc_hex)
        ciphertext, nonce = encrypt_vpa(
            key_bytes=enc_key,
            plaintext=vpa,
            associated_data=actor.public_id,
        )

        users_repo.upsert_user_pii(
            session=session,
            user_id=actor.id,
            ciphertext=ciphertext,
            nonce=nonce,
            key_id=kid,
            blind_index=blind_index,
        )

    return mask_vpa(vpa)


def get_decrypted_user_vpa(
    session: Session,
    user_id: int,
    user_public_id: str,
    key_provider: KeyProvider,
) -> str | None:
    """Retrieve and decrypt user VPA using associated data."""
    pii = users_repo.get_user_pii(session, user_id)
    if pii is None:
        return None

    enc_hex = key_provider.get_encryption_key(pii.vpa_key_id)
    if enc_hex is None:
        return None

    enc_key = bytes.fromhex(enc_hex)
    try:
        return decrypt_vpa(
            key_bytes=enc_key,
            ciphertext=pii.vpa_ciphertext,
            nonce=pii.vpa_nonce,
            associated_data=user_public_id,
        )
    except Exception:
        return None


def get_masked_user_vpa(
    session: Session,
    user_id: int,
    user_public_id: str,
    key_provider: KeyProvider,
) -> str | None:
    """Retrieve masked representation of user's VPA."""
    vpa = get_decrypted_user_vpa(session, user_id, user_public_id, key_provider)
    if vpa is None:
        return None
    return mask_vpa(vpa)
