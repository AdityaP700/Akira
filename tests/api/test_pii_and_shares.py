"""Tests for PII protection (encrypted VPA, blind index) and SHARES split strategy."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.adapters.keys import EnvKeyProvider
from app.adapters.payment_provider import MockPaymentProvider
from app.api.deps import get_db, get_key_provider, get_payment_provider
from app.core.db import Base
from app.main import app
from app.repositories.models import Expense, ExpenseShare, UserPii
from app.security.pii import PiiDecryptionError, decrypt_vpa


@pytest.fixture
def client_and_db() -> tuple[TestClient, Session, EnvKeyProvider, MockPaymentProvider]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    key_provider = EnvKeyProvider(
        key_id="test_wh_key",
        secret_hex="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",  # noqa: S106
        audit_key_id="test_audit_key",
        audit_secret_hex="abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",  # noqa: S106
        pii_key_id="test_pii_key",
        pii_enc_hex="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",  # noqa: S106
        pii_blind_hex="fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210",  # noqa: S106
    )
    payment_provider = MockPaymentProvider()

    def override_get_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    def override_get_key_provider():
        return key_provider

    def override_get_payment_provider():
        return payment_provider

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_key_provider] = override_get_key_provider
    app.dependency_overrides[get_payment_provider] = override_get_payment_provider

    db_session = session_factory()
    client = TestClient(app)

    yield client, db_session, key_provider, payment_provider

    db_session.close()
    app.dependency_overrides.clear()


def _create_user(client: TestClient, name: str) -> tuple[dict, str]:
    resp = client.post("/users", json={"name": name})
    assert resp.status_code == 201
    data = resp.json()
    token = data["api_token"]
    user = data["user"]
    return user, token


def test_vpa_raw_db_contains_no_plaintext(client_and_db) -> None:
    client, db, _, _ = client_and_db
    user, token = _create_user(client, "Alice")
    raw_vpa = "alice@okhdfcbank"

    # Set VPA via API
    resp = client.put(
        "/users/me/vpa",
        headers={"Authorization": f"Bearer {token}"},
        json={"vpa": raw_vpa},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["vpa_masked"] == "al***@okhdfcbank"

    # Query raw database row directly using raw SQL
    row = db.execute(
        text("SELECT user_id, vpa_ciphertext, vpa_nonce, vpa_key_id, vpa_blind_index FROM user_pii")
    ).fetchone()
    assert row is not None
    user_id, ciphertext, nonce, key_id, blind_index = row

    # Assert ciphertext and nonce are bytes
    assert isinstance(ciphertext, bytes)
    assert isinstance(nonce, bytes)
    assert len(nonce) == 12

    # Assert plaintext string or substring is nowhere in the database row
    assert b"alice@okhdfcbank" not in ciphertext
    assert b"alice" not in ciphertext
    assert b"alice" not in nonce
    assert "alice" not in blind_index
    assert "alice" not in key_id


def test_vpa_decryption_round_trip_and_tamper_detection(client_and_db) -> None:
    client, db, key_provider, _ = client_and_db
    user, token = _create_user(client, "Bob")
    raw_vpa = "bob@upi"

    client.put(
        "/users/me/vpa",
        headers={"Authorization": f"Bearer {token}"},
        json={"vpa": raw_vpa},
    )

    pii_row = db.scalar(select(UserPii))
    assert pii_row is not None

    enc_hex = key_provider.get_encryption_key(pii_row.vpa_key_id)
    assert enc_hex is not None
    enc_key = bytes.fromhex(enc_hex)

    # 1. Valid decrypt round trip with correct associated data (user public ID)
    decrypted = decrypt_vpa(
        key_bytes=enc_key,
        ciphertext=pii_row.vpa_ciphertext,
        nonce=pii_row.vpa_nonce,
        associated_data=user["id"],
    )
    assert decrypted == raw_vpa

    # 2. Tampered ciphertext fails (InvalidTag -> PiiDecryptionError)
    tampered_ct = bytearray(pii_row.vpa_ciphertext)
    tampered_ct[0] ^= 0xFF
    with pytest.raises(PiiDecryptionError):
        decrypt_vpa(
            key_bytes=enc_key,
            ciphertext=bytes(tampered_ct),
            nonce=pii_row.vpa_nonce,
            associated_data=user["id"],
        )

    # 3. Wrong associated data fails (binds ciphertext strictly to its owner)
    with pytest.raises(PiiDecryptionError):
        decrypt_vpa(
            key_bytes=enc_key,
            ciphertext=pii_row.vpa_ciphertext,
            nonce=pii_row.vpa_nonce,
            associated_data="usr_wrong_user_id",
        )

    # 4. Wrong key fails
    wrong_key = b"\x00" * 32
    with pytest.raises(PiiDecryptionError):
        decrypt_vpa(
            key_bytes=wrong_key,
            ciphertext=pii_row.vpa_ciphertext,
            nonce=pii_row.vpa_nonce,
            associated_data=user["id"],
        )


def test_vpa_blind_index_lookup_and_conflict(client_and_db) -> None:
    client, _, _, _ = client_and_db
    user_a, token_a = _create_user(client, "UserA")
    user_b, token_b = _create_user(client, "UserB")

    # User A registers VPA
    resp_a = client.put(
        "/users/me/vpa",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"vpa": "shared@bank"},
    )
    assert resp_a.status_code == 200

    # User B attempts to register the exact same VPA -> 409 Conflict
    resp_b1 = client.put(
        "/users/me/vpa",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"vpa": "shared@bank"},
    )
    assert resp_b1.status_code == 409
    assert resp_b1.json()["error"]["code"] == "VPA_ALREADY_IN_USE"

    # User B attempts with case and whitespace variation -> normalised blind index detects conflict
    resp_b2 = client.put(
        "/users/me/vpa",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"vpa": "  SHARED@BANK  "},
    )
    assert resp_b2.status_code == 409
    assert resp_b2.json()["error"]["code"] == "VPA_ALREADY_IN_USE"

    # User A can update their own VPA without 409 conflict
    resp_a_update = client.put(
        "/users/me/vpa",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"vpa": "shared_new@bank"},
    )
    assert resp_a_update.status_code == 200
    assert resp_a_update.json()["vpa_masked"] == "sh***@bank"


def test_user_profile_masked_vpa(client_and_db) -> None:
    client, _, _, _ = client_and_db
    user, token = _create_user(client, "Charlie")

    # Before setting VPA
    resp_me1 = client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
    assert resp_me1.status_code == 200
    assert resp_me1.json()["vpa_masked"] is None

    # Set VPA
    client.put(
        "/users/me/vpa",
        headers={"Authorization": f"Bearer {token}"},
        json={"vpa": "charlie@okaxis"},
    )

    # After setting VPA: masked representation only
    resp_me2 = client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
    assert resp_me2.status_code == 200
    assert resp_me2.json()["vpa_masked"] == "ch***@okaxis"


def test_vpa_format_validation(client_and_db) -> None:
    client, _, _, _ = client_and_db
    _, token = _create_user(client, "Dave")

    invalid_vpas = ["not-a-vpa", "@bank", "user@", "u@b", "   ", "user @bank"]
    for bad in invalid_vpas:
        resp = client.put(
            "/users/me/vpa",
            headers={"Authorization": f"Bearer {token}"},
            json={"vpa": bad},
        )
        assert resp.status_code == 422


def test_settlement_upi_link_uses_decrypted_payee_vpa(client_and_db) -> None:
    client, _, _, _ = client_and_db
    alice, token_alice = _create_user(client, "Alice")
    bob, token_bob = _create_user(client, "Bob")

    # Bob sets his VPA
    client.put(
        "/users/me/vpa",
        headers={"Authorization": f"Bearer {token_bob}"},
        json={"vpa": "bob@hdfcbank"},
    )

    # Create group and add members
    grp_resp = client.post(
        "/groups",
        headers={"Authorization": f"Bearer {token_alice}"},
        json={"name": "Trip"},
    )
    group_id = grp_resp.json()["id"]

    client.post(
        f"/groups/{group_id}/members",
        headers={"Authorization": f"Bearer {token_alice}"},
        json={"user_id": bob["id"]},
    )

    # Bob pays for an expense of ₹200.00 split equally (Alice owes Bob ₹100.00)
    client.post(
        f"/groups/{group_id}/expenses",
        headers={"Authorization": f"Bearer {token_bob}"},
        json={
            "paid_by": bob["id"],
            "amount": "200.00",
            "description": "Lunch",
            "split_type": "EQUAL",
        },
    )

    # Alice initiates a UPI settlement repayment to Bob without specifying payee_vpa
    stl_resp = client.post(
        f"/groups/{group_id}/settlements",
        headers={"Authorization": f"Bearer {token_alice}"},
        json={
            "from_user": alice["id"],
            "to_user": bob["id"],
            "amount": "100.00",
            "method": "UPI",
        },
    )
    assert stl_resp.status_code == 201
    stl_data = stl_resp.json()
    assert stl_data["status"] == "PENDING"
    assert stl_data["method"] == "UPI"
    assert stl_data["upi_link"] is not None
    # Verify the deep link contains Bob's decrypted VPA
    assert "pa=bob@hdfcbank" in stl_data["upi_link"]


def test_shares_split_proportions_and_remainder(client_and_db) -> None:
    client, db, _, _ = client_and_db
    alice, token_alice = _create_user(client, "Alice")
    bob, _ = _create_user(client, "Bob")
    charlie, _ = _create_user(client, "Charlie")

    # Create group and add members
    grp_resp = client.post(
        "/groups",
        headers={"Authorization": f"Bearer {token_alice}"},
        json={"name": "Housemates"},
    )
    group_id = grp_resp.json()["id"]
    client.post(
        f"/groups/{group_id}/members",
        headers={"Authorization": f"Bearer {token_alice}"},
        json={"user_id": bob["id"]},
    )
    client.post(
        f"/groups/{group_id}/members",
        headers={"Authorization": f"Bearer {token_alice}"},
        json={"user_id": charlie["id"]},
    )

    # 1. ₹10.00 (1000 paise) split 2:1:1 -> 500, 250, 250
    exp_resp1 = client.post(
        f"/groups/{group_id}/expenses",
        headers={"Authorization": f"Bearer {token_alice}"},
        json={
            "paid_by": alice["id"],
            "amount": "10.00",
            "description": "Groceries",
            "split_type": "SHARES",
            "shares": [
                {"user_id": alice["id"], "weight": 2},
                {"user_id": bob["id"], "weight": 1},
                {"user_id": charlie["id"], "weight": 1},
            ],
        },
    )
    assert exp_resp1.status_code == 201
    exp1_data = exp_resp1.json()
    assert exp1_data["amount"] == "10.00"
    shares1 = {s["user_id"]: s["amount"] for s in exp1_data["shares"]}
    assert shares1[alice["id"]] == "5.00"
    assert shares1[bob["id"]] == "2.50"
    assert shares1[charlie["id"]] == "2.50"

    # 2. ₹1.00 (100 paise) split 1:1:1 -> 34 paise for lowest user ID, 33 for others
    exp_resp2 = client.post(
        f"/groups/{group_id}/expenses",
        headers={"Authorization": f"Bearer {token_alice}"},
        json={
            "paid_by": alice["id"],
            "amount": "1.00",
            "description": "Salt",
            "split_type": "SHARES",
            "shares": [
                {"user_id": alice["id"], "weight": 1},
                {"user_id": bob["id"], "weight": 1},
                {"user_id": charlie["id"], "weight": 1},
            ],
        },
    )
    assert exp_resp2.status_code == 201
    exp2_data = exp_resp2.json()

    # Verify database shares sum to exact 100 paise
    db_exp2 = db.scalar(select(Expense).where(Expense.public_id == exp2_data["id"]))
    assert db_exp2 is not None
    db_shares2 = list(
        db.scalars(select(ExpenseShare).where(ExpenseShare.expense_id == db_exp2.id)).all()
    )
    assert sum(s.owed_paise for s in db_shares2) == 100

    # Verify deterministic allocation: lowest internal user id received 34 paise
    sorted_shares = sorted(db_shares2, key=lambda s: s.user_id)
    assert sorted_shares[0].owed_paise == 34
    assert sorted_shares[1].owed_paise == 33
    assert sorted_shares[2].owed_paise == 33


def test_shares_split_validations(client_and_db) -> None:
    client, _, _, _ = client_and_db
    alice, token_alice = _create_user(client, "Alice")
    bob, _ = _create_user(client, "Bob")

    grp_resp = client.post(
        "/groups",
        headers={"Authorization": f"Bearer {token_alice}"},
        json={"name": "Trip"},
    )
    group_id = grp_resp.json()["id"]

    # Missing shares list -> 422
    resp1 = client.post(
        f"/groups/{group_id}/expenses",
        headers={"Authorization": f"Bearer {token_alice}"},
        json={
            "paid_by": alice["id"],
            "amount": "100.00",
            "description": "Test",
            "split_type": "SHARES",
        },
    )
    assert resp1.status_code == 422

    # Weight 0 -> 422
    resp2 = client.post(
        f"/groups/{group_id}/expenses",
        headers={"Authorization": f"Bearer {token_alice}"},
        json={
            "paid_by": alice["id"],
            "amount": "100.00",
            "description": "Test",
            "split_type": "SHARES",
            "shares": [{"user_id": alice["id"], "weight": 0}],
        },
    )
    assert resp2.status_code == 422

    # Participant not in group -> 422 PARTICIPANT_NOT_MEMBER
    resp3 = client.post(
        f"/groups/{group_id}/expenses",
        headers={"Authorization": f"Bearer {token_alice}"},
        json={
            "paid_by": alice["id"],
            "amount": "100.00",
            "description": "Test",
            "split_type": "SHARES",
            "shares": [
                {"user_id": alice["id"], "weight": 1},
                {"user_id": bob["id"], "weight": 1},
            ],
        },
    )
    assert resp3.status_code == 422
    assert resp3.json()["error"]["code"] == "PARTICIPANT_NOT_MEMBER"


def test_db_roles_least_privilege_grants_and_policy() -> None:
    from pathlib import Path

    sql_file = Path("scripts/init_db_roles.sql")
    assert sql_file.exists(), "scripts/init_db_roles.sql must exist"

    sql_content = sql_file.read_text(encoding="utf-8")

    # Assert app_owner and app_rw roles are defined
    assert "CREATE ROLE app_owner" in sql_content
    assert "CREATE ROLE app_rw" in sql_content

    # Assert append-only tables are granted ONLY SELECT, INSERT (no UPDATE, no DELETE) to app_rw
    assert "GRANT SELECT, INSERT ON TABLE ledger_entries TO app_rw;" in sql_content
    assert "GRANT SELECT, INSERT ON TABLE expense_shares TO app_rw;" in sql_content
    assert "GRANT SELECT, INSERT ON TABLE provider_events TO app_rw;" in sql_content

    # Assert notifications table has UPDATE on read_at only
    assert "GRANT SELECT, INSERT ON TABLE notifications TO app_rw;" in sql_content
    assert "GRANT UPDATE (read_at) ON TABLE notifications TO app_rw;" in sql_content

    # Assert app_rw is NEVER granted UPDATE or DELETE on append-only tables
    lines = [line.strip().upper() for line in sql_content.splitlines()]
    for line in lines:
        if "TO APP_RW" in line:
            if "LEDGER_ENTRIES" in line:
                assert "UPDATE" not in line and "DELETE" not in line
            if "EXPENSE_SHARES" in line:
                assert "UPDATE" not in line and "DELETE" not in line
            if "PROVIDER_EVENTS" in line:
                assert "UPDATE" not in line and "DELETE" not in line
