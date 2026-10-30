"""Repository for immutable, append-only ledger entries."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.keys import EnvKeyProvider, KeyProvider
from app.domain.audit import GENESIS_PREV_HASH, canonical_json, compute_entry_hash
from app.repositories.models import Group, LedgerEntry


def append(
    session: Session,
    group_id: int,
    entry_type: str,
    ref_id: int,
    payload: dict[str, Any],
    key_provider: KeyProvider | None = None,
    created_at: datetime | None = None,
) -> LedgerEntry:
    """Append a new entry to the group's ledger with HMAC-SHA256 hash chaining.

    Precondition: The group row MUST already be locked using lock_for_update.
    Increments ledger_head_seq monotonically and computes
    entry_hash = HMAC(key, prev_hash || canonical_json(entry)).
    """
    group = session.get(Group, group_id)
    if group is None:
        raise ValueError(f"Cannot append to ledger: group {group_id} not found")

    if key_provider is None:
        key_provider = EnvKeyProvider()

    kid, secret_hex = key_provider.get_current_audit_key()
    next_seq = group.ledger_head_seq + 1
    prev_hash = group.ledger_head_hash or GENESIS_PREV_HASH
    entry_time = created_at or datetime.now(UTC)

    # Canonical dictionary representing the ledger entry
    entry_dict = {
        "created_at": entry_time.isoformat(),
        "entry_type": entry_type,
        "group_id": group_id,
        "payload": payload,
        "ref_id": ref_id,
        "seq": next_seq,
    }
    canonical_str = canonical_json(entry_dict)
    entry_hash = compute_entry_hash(secret_hex, prev_hash, canonical_str)

    entry = LedgerEntry(
        group_id=group_id,
        seq=next_seq,
        entry_type=entry_type,
        ref_id=ref_id,
        payload=payload,
        prev_hash=prev_hash,
        entry_hash=entry_hash,
        key_id=kid,
        created_at=entry_time,
    )
    session.add(entry)
    group.ledger_head_seq = next_seq
    group.ledger_head_hash = entry_hash
    session.flush()
    return entry


def list_by_group(session: Session, group_id: int) -> list[LedgerEntry]:
    """Retrieve all ledger entries for a group in sequence order."""
    stmt = (
        select(LedgerEntry).where(LedgerEntry.group_id == group_id).order_by(LedgerEntry.seq.asc())
    )
    return list(session.scalars(stmt).all())
