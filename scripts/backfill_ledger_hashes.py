"""One-off backfill script to compute HMAC hash chains for unhashed legacy ledger entries."""

from datetime import UTC

from sqlalchemy import select

from app.adapters.keys import EnvKeyProvider
from app.core.db import SessionLocal
from app.domain.audit import GENESIS_PREV_HASH, canonical_json, compute_entry_hash
from app.repositories.models import Group, LedgerEntry


def backfill_group(session: SessionLocal, group: Group, key_provider: EnvKeyProvider) -> int:  # type: ignore[valid-type]
    """Backfill HMAC hash chain for a single group in sequence order."""
    entries = list(
        session.scalars(
            select(LedgerEntry)
            .where(LedgerEntry.group_id == group.id)
            .order_by(LedgerEntry.seq.asc())
        ).all()
    )
    if not entries:
        return 0

    kid, secret_hex = key_provider.get_current_audit_key()
    prev_hash = GENESIS_PREV_HASH
    backfilled_count = 0

    for entry in entries:
        if entry.entry_hash is not None and entry.prev_hash is not None:
            prev_hash = entry.entry_hash
            continue

        created_at_val = entry.created_at
        if created_at_val.tzinfo is None:
            created_at_val = created_at_val.replace(tzinfo=UTC)
        else:
            created_at_val = created_at_val.astimezone(UTC)

        entry_dict = {
            "created_at": created_at_val.isoformat(),
            "entry_type": entry.entry_type,
            "group_id": entry.group_id,
            "payload": entry.payload,
            "ref_id": entry.ref_id,
            "seq": entry.seq,
        }
        canonical_str = canonical_json(entry_dict)
        entry_hash = compute_entry_hash(secret_hex, prev_hash, canonical_str)

        entry.prev_hash = prev_hash
        entry.entry_hash = entry_hash
        entry.key_id = kid
        prev_hash = entry_hash
        backfilled_count += 1

    group.ledger_head_hash = prev_hash
    return backfilled_count


def backfill_all() -> None:
    key_provider = EnvKeyProvider()
    total_backfilled = 0

    with SessionLocal() as session:
        with session.begin():
            groups = list(session.scalars(select(Group)).all())
            for group in groups:
                count = backfill_group(session, group, key_provider)
                total_backfilled += count

    print(
        f"Backfill complete: updated {total_backfilled} ledger entries across {len(groups)} groups."
    )


if __name__ == "__main__":
    backfill_all()
