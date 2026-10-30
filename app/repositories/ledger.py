"""Repository for immutable, append-only ledger entries."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.repositories.models import Group, LedgerEntry


def append(
    session: Session,
    group_id: int,
    entry_type: str,
    ref_id: int,
    payload: dict[str, Any],
) -> LedgerEntry:
    """Append a new entry to the group's ledger.

    Precondition: The group row MUST already be locked using lock_for_update.
    Increments ledger_head_seq monotonically and creates the corresponding ledger_entry.
    """
    group = session.get(Group, group_id)
    if group is None:
        raise ValueError(f"Cannot append to ledger: group {group_id} not found")

    next_seq = group.ledger_head_seq + 1
    entry = LedgerEntry(
        group_id=group_id,
        seq=next_seq,
        entry_type=entry_type,
        ref_id=ref_id,
        payload=payload,
    )
    session.add(entry)
    group.ledger_head_seq = next_seq
    session.flush()
    return entry


def list_by_group(session: Session, group_id: int) -> list[LedgerEntry]:
    """Retrieve all ledger entries for a group in sequence order."""
    stmt = (
        select(LedgerEntry).where(LedgerEntry.group_id == group_id).order_by(LedgerEntry.seq.asc())
    )
    return list(session.scalars(stmt).all())
