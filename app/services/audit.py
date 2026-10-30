"""Service for audit verification of tamper-evident HMAC hash-chained ledger."""

import hmac
from datetime import UTC
from typing import Any

from sqlalchemy.orm import Session

from app.adapters.keys import EnvKeyProvider, KeyProvider
from app.domain.audit import GENESIS_PREV_HASH, canonical_json, compute_entry_hash
from app.repositories import ledger as ledger_repo
from app.repositories.models import Expense, Settlement, User
from app.security.guards import require_member


def verify_group_ledger(
    session: Session,
    group_public_id: str,
    actor: User,
    key_provider: KeyProvider | None = None,
) -> dict[str, Any]:
    """Verify cryptographic integrity of a group's append-only ledger.

    1. Checks object-level authorization (caller must be a group member; non-members get 404).
    2. Validates contiguous sequence numbers starting from 1 (detects deleted rows -> seq_gap).
    3. Recomputes HMAC-SHA256 entry hashes (detects tampered hashes -> hash_mismatch).
    4. Cross-checks entry payloads against referenced expense/settlement database rows.
    5. Validates group head hash matches last entry.
    """
    group = require_member(session, group_public_id, actor)

    if key_provider is None:
        key_provider = EnvKeyProvider()

    entries = ledger_repo.list_by_group(session, group.id)

    if not entries:
        if group.ledger_head_seq == 0 and (
            group.ledger_head_hash is None or group.ledger_head_hash == GENESIS_PREV_HASH
        ):
            return {
                "valid": True,
                "entries": 0,
                "head": GENESIS_PREV_HASH,
            }
        return {
            "valid": False,
            "broken_at": 1,
            "reason": "seq_gap" if group.ledger_head_seq > 0 else "hash_mismatch",
        }

    for idx, entry in enumerate(entries):
        expected_seq = idx + 1
        # Check sequence continuity
        if entry.seq != expected_seq:
            return {
                "valid": False,
                "broken_at": expected_seq,
                "reason": "seq_gap",
            }

        # Check prev_hash linkage
        if entry.seq == 1:
            expected_prev = GENESIS_PREV_HASH
        else:
            expected_prev = entries[idx - 1].entry_hash or ""

        if entry.prev_hash != expected_prev:
            return {
                "valid": False,
                "broken_at": entry.seq,
                "reason": "hash_mismatch",
            }

        # Resolve audit key
        if not entry.key_id:
            return {
                "valid": False,
                "broken_at": entry.seq,
                "reason": "hash_mismatch",
            }

        secret_hex = key_provider.get_audit_key(entry.key_id)
        if secret_hex is None:
            return {
                "valid": False,
                "broken_at": entry.seq,
                "reason": "hash_mismatch",
            }

        # Format ISO timestamp
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
        expected_hash = compute_entry_hash(secret_hex, entry.prev_hash, canonical_str)

        if not entry.entry_hash or not hmac.compare_digest(entry.entry_hash, expected_hash):
            return {
                "valid": False,
                "broken_at": entry.seq,
                "reason": "hash_mismatch",
            }

        # Cross-check payload against referenced database row
        if entry.entry_type == "EXPENSE":
            expense = session.get(Expense, entry.ref_id)
            if expense is None:
                return {
                    "valid": False,
                    "broken_at": entry.seq,
                    "reason": "hash_mismatch",
                }
            if (
                expense.amount_paise != entry.payload.get("amount_paise")
                or expense.paid_by != entry.payload.get("paid_by")
                or expense.split_type != entry.payload.get("split_type")
            ):
                return {
                    "valid": False,
                    "broken_at": entry.seq,
                    "reason": "hash_mismatch",
                }
        elif entry.entry_type == "SETTLEMENT":
            settlement = session.get(Settlement, entry.ref_id)
            if settlement is None:
                return {
                    "valid": False,
                    "broken_at": entry.seq,
                    "reason": "hash_mismatch",
                }
            if (
                settlement.amount_paise != entry.payload.get("amount_paise")
                or settlement.from_user != entry.payload.get("from_user")
                or settlement.to_user != entry.payload.get("to_user")
            ):
                return {
                    "valid": False,
                    "broken_at": entry.seq,
                    "reason": "hash_mismatch",
                }

    # Verify group head alignment
    if group.ledger_head_hash != entries[-1].entry_hash:
        return {
            "valid": False,
            "broken_at": entries[-1].seq,
            "reason": "hash_mismatch",
        }

    if group.ledger_head_seq != len(entries):
        return {
            "valid": False,
            "broken_at": len(entries) + 1,
            "reason": "seq_gap",
        }

    return {
        "valid": True,
        "entries": len(entries),
        "head": entries[-1].entry_hash,
    }
