"""Tests for tamper-evident HMAC hash-chained ledger and audit verification endpoint."""

from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.keys import EnvKeyProvider
from app.api.deps import get_db, get_key_provider
from app.domain.audit import compute_entry_hash
from app.main import app
from app.repositories.models import Expense, LedgerEntry

ClientDbProvider = tuple[TestClient, Session, EnvKeyProvider]


@pytest.fixture
def client_and_db(
    session_factory: sessionmaker,
) -> Generator[ClientDbProvider, None, None]:
    key_provider = EnvKeyProvider(
        key_id="test_wh_key",
        secret_hex="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",  # noqa: S106
        audit_key_id="test_audit_key",
        audit_secret_hex="abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",  # noqa: S106
    )

    def override_get_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    def override_get_key_provider():
        return key_provider

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_key_provider] = override_get_key_provider

    client = TestClient(app)
    db = session_factory()
    try:
        yield client, db, key_provider
    finally:
        db.close()
        app.dependency_overrides.clear()


def _create_user(client: TestClient, name: str) -> tuple[str, str]:
    res = client.post("/users", json={"name": name})
    assert res.status_code == 201
    data = res.json()
    return data["user"]["id"], data["api_token"]


def _setup_group(
    client: TestClient,
) -> tuple[str, str, str, str, str, str]:
    u1_id, t1 = _create_user(client, "Alice")
    u2_id, t2 = _create_user(client, "Bob")
    u3_id, t3 = _create_user(client, "Charlie")

    res_g = client.post(
        "/groups", json={"name": "Audit Trip"}, headers={"Authorization": f"Bearer {t1}"}
    )
    assert res_g.status_code == 201
    grp_id = res_g.json()["id"]

    client.post(
        f"/groups/{grp_id}/members",
        json={"user_id": u2_id},
        headers={"Authorization": f"Bearer {t1}"},
    )
    client.post(
        f"/groups/{grp_id}/members",
        json={"user_id": u3_id},
        headers={"Authorization": f"Bearer {t1}"},
    )

    return grp_id, u1_id, t1, u2_id, t2, u3_id


def test_empty_group_verifies(client_and_db: ClientDbProvider) -> None:
    client, _, _ = client_and_db
    grp_id, _, t1, _, _, _ = _setup_group(client)

    res = client.get(f"/groups/{grp_id}/audit/verify", headers={"Authorization": f"Bearer {t1}"})
    assert res.status_code == 200
    data = res.json()
    assert data["valid"] is True
    assert data["entries"] == 0
    assert data["head"] == "0" * 64


def test_chain_of_50_entries_verifies(
    client_and_db: ClientDbProvider,
) -> None:
    client, _, _ = client_and_db
    grp_id, u1_id, t1, u2_id, t2, _ = _setup_group(client)

    # Record 50 entries
    for i in range(50):
        payer_token = t1 if i % 2 == 0 else t2
        res = client.post(
            f"/groups/{grp_id}/expenses",
            json={
                "paid_by": u1_id if i % 2 == 0 else u2_id,
                "amount": f"{10 + i}.00",
                "description": f"Expense {i + 1}",
                "split_type": "EQUAL",
            },
            headers={"Authorization": f"Bearer {payer_token}"},
        )
        assert res.status_code == 201

    res_verify = client.get(
        f"/groups/{grp_id}/audit/verify", headers={"Authorization": f"Bearer {t1}"}
    )
    assert res_verify.status_code == 200
    data = res_verify.json()
    assert data["valid"] is True
    assert data["entries"] == 50
    assert len(data["head"]) == 64
    assert data["head"] != "0" * 64


def test_tampered_ledger_payload_detected(
    client_and_db: ClientDbProvider,
) -> None:
    client, db, _ = client_and_db
    grp_id, u1_id, t1, _, _, _ = _setup_group(client)

    for i in range(5):
        res = client.post(
            f"/groups/{grp_id}/expenses",
            json={
                "paid_by": u1_id,
                "amount": f"{100 * (i + 1)}.00",
                "description": f"Expense {i + 1}",
                "split_type": "EQUAL",
            },
            headers={"Authorization": f"Bearer {t1}"},
        )
        assert res.status_code == 201

    # Verify initial valid state
    res_init = client.get(
        f"/groups/{grp_id}/audit/verify", headers={"Authorization": f"Bearer {t1}"}
    )
    assert res_init.json()["valid"] is True

    # Tamper with ledger entry payload at seq 3 directly in DB
    entry = db.query(LedgerEntry).filter(LedgerEntry.seq == 3).first()
    assert entry is not None
    tampered_payload = dict(entry.payload)
    tampered_payload["amount_paise"] = 99999
    entry.payload = tampered_payload
    db.commit()

    # Audit verification detects hash mismatch at seq 3
    res_tampered = client.get(
        f"/groups/{grp_id}/audit/verify", headers={"Authorization": f"Bearer {t1}"}
    )
    assert res_tampered.status_code == 200
    data = res_tampered.json()
    assert data["valid"] is False
    assert data["broken_at"] == 3
    assert data["reason"] == "hash_mismatch"


def test_tampered_underlying_expense_row_detected(
    client_and_db: ClientDbProvider,
) -> None:
    client, db, _ = client_and_db
    grp_id, u1_id, t1, _, _, _ = _setup_group(client)

    for i in range(4):
        client.post(
            f"/groups/{grp_id}/expenses",
            json={
                "paid_by": u1_id,
                "amount": "100.00",
                "description": f"Expense {i + 1}",
                "split_type": "EQUAL",
            },
            headers={"Authorization": f"Bearer {t1}"},
        )

    # Tamper with underlying Expense row referenced by entry seq 2
    # (leaving ledger entry unchanged)
    entry_2 = db.query(LedgerEntry).filter(LedgerEntry.seq == 2).first()
    assert entry_2 is not None
    expense = db.query(Expense).filter(Expense.id == entry_2.ref_id).first()
    assert expense is not None
    expense.amount_paise = 55555  # Mutate amount without touching ledger entry
    db.commit()

    res = client.get(f"/groups/{grp_id}/audit/verify", headers={"Authorization": f"Bearer {t1}"})
    assert res.status_code == 200
    data = res.json()
    assert data["valid"] is False
    assert data["broken_at"] == 2
    assert data["reason"] == "hash_mismatch"


def test_deleted_ledger_entry_detected_as_seq_gap(
    client_and_db: ClientDbProvider,
) -> None:
    client, db, _ = client_and_db
    grp_id, u1_id, t1, _, _, _ = _setup_group(client)

    for i in range(5):
        client.post(
            f"/groups/{grp_id}/expenses",
            json={
                "paid_by": u1_id,
                "amount": "50.00",
                "description": f"Expense {i + 1}",
                "split_type": "EQUAL",
            },
            headers={"Authorization": f"Bearer {t1}"},
        )

    # Delete entry seq 3 directly from DB
    entry_3 = db.query(LedgerEntry).filter(LedgerEntry.seq == 3).first()
    assert entry_3 is not None
    db.delete(entry_3)
    db.commit()

    res = client.get(f"/groups/{grp_id}/audit/verify", headers={"Authorization": f"Bearer {t1}"})
    assert res.status_code == 200
    data = res.json()
    assert data["valid"] is False
    assert data["broken_at"] == 3
    assert data["reason"] == "seq_gap"


def test_hash_recomputed_with_wrong_key_fails(
    client_and_db: ClientDbProvider,
) -> None:
    client, db, key_provider = client_and_db
    grp_id, u1_id, t1, _, _, _ = _setup_group(client)

    for i in range(3):
        client.post(
            f"/groups/{grp_id}/expenses",
            json={
                "paid_by": u1_id,
                "amount": "100.00",
                "description": f"Expense {i + 1}",
                "split_type": "EQUAL",
            },
            headers={"Authorization": f"Bearer {t1}"},
        )

    # Forge entry 2's hash using an attacker's key
    entry_2 = db.query(LedgerEntry).filter(LedgerEntry.seq == 2).first()
    assert entry_2 is not None
    attacker_key = "1111111111111111111111111111111111111111111111111111111111111111"  # noqa: S106
    forged_hash = compute_entry_hash(attacker_key, entry_2.prev_hash, "{}")
    entry_2.entry_hash = forged_hash
    db.commit()

    res = client.get(f"/groups/{grp_id}/audit/verify", headers={"Authorization": f"Bearer {t1}"})
    assert res.status_code == 200
    data = res.json()
    assert data["valid"] is False
    assert data["broken_at"] == 2
    assert data["reason"] == "hash_mismatch"


def test_key_rotation_verification(
    client_and_db: ClientDbProvider,
) -> None:
    client, _, key_provider = client_and_db
    grp_id, u1_id, t1, _, _, _ = _setup_group(client)

    # 1. Append 2 entries with key v1
    for i in range(2):
        client.post(
            f"/groups/{grp_id}/expenses",
            json={
                "paid_by": u1_id,
                "amount": "100.00",
                "description": f"Exp {i}",
                "split_type": "EQUAL",
            },
            headers={"Authorization": f"Bearer {t1}"},
        )

    # 2. Rotate audit key to v2
    new_kid = "test_audit_key_v2"
    new_secret = "9999999999999999999999999999999999999999999999999999999999999999"  # noqa: S105, S106
    key_provider.register_audit_key(new_kid, new_secret)
    key_provider._audit_key_id = new_kid
    key_provider._audit_secret_hex = new_secret

    # 3. Append 2 entries with key v2
    for i in range(2, 4):
        client.post(
            f"/groups/{grp_id}/expenses",
            json={
                "paid_by": u1_id,
                "amount": "100.00",
                "description": f"Exp {i}",
                "split_type": "EQUAL",
            },
            headers={"Authorization": f"Bearer {t1}"},
        )

    # 4. Verify that multi-key chain verifies across both rotated keys
    res = client.get(f"/groups/{grp_id}/audit/verify", headers={"Authorization": f"Bearer {t1}"})
    assert res.status_code == 200
    data = res.json()
    assert data["valid"] is True
    assert data["entries"] == 4


def test_bola_non_member_cannot_verify_audit(
    client_and_db: ClientDbProvider,
) -> None:
    client, _, _ = client_and_db
    grp_id, _, _, _, _, _ = _setup_group(client)
    _, non_member_token = _create_user(client, "Eve")

    res = client.get(
        f"/groups/{grp_id}/audit/verify",
        headers={"Authorization": f"Bearer {non_member_token}"},
    )
    # BOLA: non-member gets identical 404 NOT_FOUND
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "NOT_FOUND"


def test_concurrent_appends_produce_consecutive_seqs_and_valid_chain(
    client_and_db: ClientDbProvider,
) -> None:
    client, _, _ = client_and_db
    grp_id, u1_id, t1, _, _, _ = _setup_group(client)

    num_threads = 10

    def post_expense(idx: int) -> int:
        r = client.post(
            f"/groups/{grp_id}/expenses",
            json={
                "paid_by": u1_id,
                "amount": f"{idx + 1}.00",
                "description": f"Parallel {idx}",
                "split_type": "EQUAL",
            },
            headers={"Authorization": f"Bearer {t1}"},
        )
        return r.status_code

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(post_expense, range(num_threads)))

    assert all(code == 201 for code in results)

    res = client.get(f"/groups/{grp_id}/audit/verify", headers={"Authorization": f"Bearer {t1}"})
    assert res.status_code == 200
    data = res.json()
    assert data["valid"] is True
    assert data["entries"] == num_threads
