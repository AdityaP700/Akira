"""Comprehensive API tests for settlement payment lifecycle, signed webhooks, and notifications."""

import json
import secrets
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.adapters.keys import EnvKeyProvider
from app.adapters.payment_provider import MockPaymentProvider
from app.api.deps import get_db, get_key_provider, get_payment_provider
from app.core.db import Base
from app.main import app
from app.security.signatures import build_signature_header


@pytest.fixture
def client_session_provider() -> tuple[TestClient, Session, MockPaymentProvider, EnvKeyProvider]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    test_provider = MockPaymentProvider()
    test_key_provider = EnvKeyProvider(
        key_id="test_key_01",
        secret_hex="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",  # noqa: S106
    )

    def override_get_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_payment_provider] = lambda: test_provider
    app.dependency_overrides[get_key_provider] = lambda: test_key_provider

    client = TestClient(app)
    test_session = session_factory()
    try:
        yield client, test_session, test_provider, test_key_provider
    finally:
        test_session.close()
        app.dependency_overrides.clear()


def _setup_group_with_debt(
    client: TestClient,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    """Setup Alice and Bob in a group, Alice pays ₹1000 dinner -> Bob owes ₹500."""
    res_a = client.post("/users", json={"name": "Alice"})
    assert res_a.status_code == 201
    alice = res_a.json()

    res_b = client.post("/users", json={"name": "Bob"})
    assert res_b.status_code == 201
    bob = res_b.json()

    # Alice creates group
    client.headers["Authorization"] = f"Bearer {alice['api_token']}"
    res_g = client.post("/groups", json={"name": "Goa Trip"})
    assert res_g.status_code == 201
    group_id = res_g.json()["id"]

    # Alice adds Bob
    res_m = client.post(f"/groups/{group_id}/members", json={"user_id": bob["id"]})
    assert res_m.status_code == 201

    # Alice creates ₹1000 dinner expense (Equal split)
    res_e = client.post(
        f"/groups/{group_id}/expenses",
        json={
            "description": "Seafood Dinner",
            "amount": "1000.00",
            "paid_by": alice["id"],
            "split_type": "EQUAL",
        },
    )
    assert res_e.status_code == 201

    return alice, bob, group_id


def test_happy_upi_settlement_lifecycle(
    client_session_provider: tuple[TestClient, Session, MockPaymentProvider, EnvKeyProvider],
) -> None:
    client, _, _, key_provider = client_session_provider
    alice, bob, group_id = _setup_group_with_debt(client)

    # Bob initiates UPI settlement for ₹500 to Alice
    client.headers["Authorization"] = f"Bearer {bob['api_token']}"
    res_stl = client.post(
        f"/groups/{group_id}/settlements",
        json={
            "from_user": bob["id"],
            "to_user": alice["id"],
            "amount": "500.00",
            "method": "UPI",
            "payee_vpa": "alice@upi",
        },
    )
    assert res_stl.status_code == 201
    stl = res_stl.json()
    assert stl["status"] == "PENDING"
    assert stl["method"] == "UPI"
    assert stl["reference"].startswith("ref_")
    assert stl["upi_link"].startswith("upi://pay?pa=alice@upi&am=500.00&tr=ref_")

    # Balances before webhook: Bob still owes Alice ₹500 (PENDING does not change balance)
    res_bal = client.get(f"/groups/{group_id}/balances")
    assert res_bal.status_code == 200
    assert res_bal.json()["balances"]["Bob"]["owes"]["Alice"] == "500.00"

    # Send signed webhook callback with status SUCCESS
    event_id = f"evt_{secrets.token_hex(12)}"
    payload_dict = {
        "event_id": event_id,
        "reference": stl["reference"],
        "status": "SUCCESS",
        "amount": "500.00",
    }
    raw_body = json.dumps(payload_dict, separators=(",", ":")).encode()

    kid, secret_hex = key_provider.get_current_webhook_key()
    signature = build_signature_header(kid, secret_hex, raw_body)

    # Clear auth header for webhook
    client.headers.pop("Authorization", None)
    res_wh = client.post(
        "/webhooks/mock-provider",
        content=raw_body,
        headers={"Content-Type": "application/json", "X-Provider-Signature": signature},
    )
    assert res_wh.status_code == 200
    assert res_wh.json()["new_status"] == "SUCCESS"

    # Balances after webhook: Debt is settled (0.00)
    client.headers["Authorization"] = f"Bearer {alice['api_token']}"
    res_bal_after = client.get(f"/groups/{group_id}/balances")
    assert res_bal_after.status_code == 200
    assert "Bob" not in res_bal_after.json()["balances"]


def test_webhook_signatures_rejection_suite(
    client_session_provider: tuple[TestClient, Session, MockPaymentProvider, EnvKeyProvider],
) -> None:
    client, _, _, key_provider = client_session_provider
    alice, bob, group_id = _setup_group_with_debt(client)

    client.headers["Authorization"] = f"Bearer {bob['api_token']}"
    res_stl = client.post(
        f"/groups/{group_id}/settlements",
        json={
            "from_user": bob["id"],
            "to_user": alice["id"],
            "amount": "500.00",
            "method": "UPI",
        },
    )
    assert res_stl.status_code == 201
    stl = res_stl.json()
    ref = stl["reference"]

    client.headers.pop("Authorization", None)
    kid, secret_hex = key_provider.get_current_webhook_key()

    payload_dict = {
        "event_id": f"evt_{secrets.token_hex(12)}",
        "reference": ref,
        "status": "SUCCESS",
        "amount": "500.00",
    }
    raw_body = json.dumps(payload_dict, separators=(",", ":")).encode()

    # 1. Missing header
    res1 = client.post(
        "/webhooks/mock-provider", content=raw_body, headers={"Content-Type": "application/json"}
    )
    assert res1.status_code == 401
    assert res1.json()["error"]["code"] == "INVALID_SIGNATURE"

    # 2. Forged signature
    res2 = client.post(
        "/webhooks/mock-provider",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-Provider-Signature": f"kid={kid},t={int(time.time())},v1={'0' * 64}",
        },
    )
    assert res2.status_code == 401
    assert res2.json()["error"]["code"] == "INVALID_SIGNATURE"

    # 3. Unknown kid
    res3 = client.post(
        "/webhooks/mock-provider",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-Provider-Signature": f"kid=nonexistent,t={int(time.time())},v1={'0' * 64}",
        },
    )
    assert res3.status_code == 401
    assert res3.json()["error"]["code"] == "UNKNOWN_KEY_ID"

    # 4. Stale timestamp (older than 300s)
    stale_t = int(time.time()) - 400
    stale_sig = build_signature_header(kid, secret_hex, raw_body, timestamp=stale_t)
    res4 = client.post(
        "/webhooks/mock-provider",
        content=raw_body,
        headers={"Content-Type": "application/json", "X-Provider-Signature": stale_sig},
    )
    assert res4.status_code == 401
    assert res4.json()["error"]["code"] == "STALE_TIMESTAMP"

    # 5. Tampered body
    valid_sig = build_signature_header(kid, secret_hex, raw_body)
    tampered_body = raw_body.replace(b"500.00", b"100.00")
    res5 = client.post(
        "/webhooks/mock-provider",
        content=tampered_body,
        headers={"Content-Type": "application/json", "X-Provider-Signature": valid_sig},
    )
    assert res5.status_code == 401
    assert res5.json()["error"]["code"] == "INVALID_SIGNATURE"

    # 6. Amount mismatch (signature valid for modified body,
    # but body amount does not match settlement)
    mismatch_payload = {
        "event_id": f"evt_{secrets.token_hex(12)}",
        "reference": ref,
        "status": "SUCCESS",
        "amount": "600.00",
    }
    mismatch_body = json.dumps(mismatch_payload, separators=(",", ":")).encode()
    mismatch_sig = build_signature_header(kid, secret_hex, mismatch_body)
    res6 = client.post(
        "/webhooks/mock-provider",
        content=mismatch_body,
        headers={"Content-Type": "application/json", "X-Provider-Signature": mismatch_sig},
    )
    assert res6.status_code == 422
    assert res6.json()["error"]["code"] == "VALIDATION_ERROR"

    # Status remains PENDING throughout
    client.headers["Authorization"] = f"Bearer {bob['api_token']}"
    res_list = client.get(f"/groups/{group_id}/settlements")
    assert res_list.status_code == 200
    assert res_list.json()["items"][0]["status"] == "PENDING"


def test_duplicate_webhook_deduplication_and_late_event(
    client_session_provider: tuple[TestClient, Session, MockPaymentProvider, EnvKeyProvider],
) -> None:
    client, _, _, key_provider = client_session_provider
    alice, bob, group_id = _setup_group_with_debt(client)

    client.headers["Authorization"] = f"Bearer {bob['api_token']}"
    res_stl = client.post(
        f"/groups/{group_id}/settlements",
        json={
            "from_user": bob["id"],
            "to_user": alice["id"],
            "amount": "500.00",
            "method": "UPI",
        },
    )
    stl = res_stl.json()
    ref = stl["reference"]

    client.headers.pop("Authorization", None)
    kid, secret_hex = key_provider.get_current_webhook_key()

    evt_id = f"evt_{secrets.token_hex(12)}"
    payload_success = {
        "event_id": evt_id,
        "reference": ref,
        "status": "SUCCESS",
        "amount": "500.00",
    }
    raw_success = json.dumps(payload_success, separators=(",", ":")).encode()
    sig_success = build_signature_header(kid, secret_hex, raw_success)

    # First delivery: success
    res1 = client.post(
        "/webhooks/mock-provider",
        content=raw_success,
        headers={"Content-Type": "application/json", "X-Provider-Signature": sig_success},
    )
    assert res1.status_code == 200
    assert res1.json()["new_status"] == "SUCCESS"

    # Duplicate delivery with same event_id: returns 200 no-op
    res2 = client.post(
        "/webhooks/mock-provider",
        content=raw_success,
        headers={"Content-Type": "application/json", "X-Provider-Signature": sig_success},
    )
    assert res2.status_code == 200
    assert res2.json()["message"] == "Duplicate event ignored"

    # Late out-of-order FAILED event with new event_id
    payload_failed = {
        "event_id": f"evt_{secrets.token_hex(12)}",
        "reference": ref,
        "status": "FAILED",
        "amount": "500.00",
    }
    raw_failed = json.dumps(payload_failed, separators=(",", ":")).encode()
    sig_failed = build_signature_header(kid, secret_hex, raw_failed)
    res3 = client.post(
        "/webhooks/mock-provider",
        content=raw_failed,
        headers={"Content-Type": "application/json", "X-Provider-Signature": sig_failed},
    )
    assert res3.status_code == 200
    assert "ignored" in res3.json()["message"]

    # Status remains SUCCESS
    client.headers["Authorization"] = f"Bearer {alice['api_token']}"
    res_list = client.get(f"/groups/{group_id}/settlements")
    assert res_list.json()["items"][0]["status"] == "SUCCESS"


def test_refresh_fallback_resolves_missed_webhook(
    client_session_provider: tuple[TestClient, Session, MockPaymentProvider, EnvKeyProvider],
) -> None:
    client, _, provider, _ = client_session_provider
    alice, bob, group_id = _setup_group_with_debt(client)

    client.headers["Authorization"] = f"Bearer {bob['api_token']}"
    res_stl = client.post(
        f"/groups/{group_id}/settlements",
        json={
            "from_user": bob["id"],
            "to_user": alice["id"],
            "amount": "500.00",
            "method": "UPI",
        },
    )
    stl = res_stl.json()
    ref = stl["reference"]
    stl_id = stl["id"]

    # Simulate provider received settlement payment (webhook missed by network)
    provider.set_status(ref, "SUCCESS")

    # Call refresh endpoint
    res_ref = client.post(f"/groups/{group_id}/settlements/{stl_id}/refresh")
    assert res_ref.status_code == 200
    assert res_ref.json()["status"] == "SUCCESS"

    # Balances reflect success
    res_bal = client.get(f"/groups/{group_id}/balances")
    assert "Bob" not in res_bal.json()["balances"]


def test_manual_claim_confirm_and_reject_flow(
    client_session_provider: tuple[TestClient, Session, MockPaymentProvider, EnvKeyProvider],
) -> None:
    client, _, _, _ = client_session_provider
    alice, bob, group_id = _setup_group_with_debt(client)

    # 1. Payer (Bob) claims cash payment
    client.headers["Authorization"] = f"Bearer {bob['api_token']}"
    res_claim = client.post(
        f"/groups/{group_id}/settlements",
        json={
            "from_user": bob["id"],
            "to_user": alice["id"],
            "amount": "500.00",
            "method": "CASH",
        },
    )
    assert res_claim.status_code == 201
    claim = res_claim.json()
    assert claim["status"] == "CLAIMED"
    stl_id = claim["id"]

    # Balances unaffected by CLAIMED
    res_bal = client.get(f"/groups/{group_id}/balances")
    assert res_bal.json()["balances"]["Bob"]["owes"]["Alice"] == "500.00"

    # Bob (payer) trying to confirm own claim -> 404
    res_bad_confirm = client.post(f"/groups/{group_id}/settlements/{stl_id}/confirm")
    assert res_bad_confirm.status_code == 404

    # Alice (receiver) confirms the claim
    client.headers["Authorization"] = f"Bearer {alice['api_token']}"
    res_ok_confirm = client.post(f"/groups/{group_id}/settlements/{stl_id}/confirm")
    assert res_ok_confirm.status_code == 200
    assert res_ok_confirm.json()["status"] == "CONFIRMED"

    # Debt settled
    res_bal_after = client.get(f"/groups/{group_id}/balances")
    assert "Bob" not in res_bal_after.json()["balances"]

    # 2. Second debt scenario: rejection
    # Alice adds another ₹600 expense (Bob owes ₹300)
    res_e2 = client.post(
        f"/groups/{group_id}/expenses",
        json={
            "description": "Cab",
            "amount": "600.00",
            "paid_by": alice["id"],
            "split_type": "EQUAL",
        },
    )
    assert res_e2.status_code == 201

    # Bob claims ₹300
    client.headers["Authorization"] = f"Bearer {bob['api_token']}"
    res_claim2 = client.post(
        f"/groups/{group_id}/settlements",
        json={
            "from_user": bob["id"],
            "to_user": alice["id"],
            "amount": "300.00",
            "method": "CASH",
        },
    )
    stl_id2 = res_claim2.json()["id"]

    # Alice rejects
    client.headers["Authorization"] = f"Bearer {alice['api_token']}"
    res_reject = client.post(f"/groups/{group_id}/settlements/{stl_id2}/reject")
    assert res_reject.status_code == 200
    assert res_reject.json()["status"] == "REJECTED"

    # Debt remains ₹300
    res_bal_after_rej = client.get(f"/groups/{group_id}/balances")
    assert res_bal_after_rej.json()["balances"]["Bob"]["owes"]["Alice"] == "300.00"

    # 3. Direct settlement: Alice records money received -> immediately CONFIRMED
    res_direct = client.post(
        f"/groups/{group_id}/settlements",
        json={
            "from_user": bob["id"],
            "to_user": alice["id"],
            "amount": "300.00",
            "method": "CASH",
        },
    )
    assert res_direct.status_code == 201
    assert res_direct.json()["status"] == "CONFIRMED"

    # Final balance: 0
    res_bal_final = client.get(f"/groups/{group_id}/balances")
    assert "Bob" not in res_bal_final.json()["balances"]


def test_concurrent_settlements_debt_capacity_reservation(
    client_session_provider: tuple[TestClient, Session, MockPaymentProvider, EnvKeyProvider],
) -> None:
    client, _, _, _ = client_session_provider
    alice, bob, group_id = _setup_group_with_debt(client)

    # Bob owes Alice ₹500
    # Bob initiates ₹500 settlement (UPI PENDING)
    client.headers["Authorization"] = f"Bearer {bob['api_token']}"
    res1 = client.post(
        f"/groups/{group_id}/settlements",
        json={
            "from_user": bob["id"],
            "to_user": alice["id"],
            "amount": "500.00",
            "method": "UPI",
        },
    )
    assert res1.status_code == 201

    # While ₹500 is PENDING, second settlement for the same debt is rejected
    res2 = client.post(
        f"/groups/{group_id}/settlements",
        json={
            "from_user": bob["id"],
            "to_user": alice["id"],
            "amount": "500.00",
            "method": "UPI",
        },
    )
    assert res2.status_code == 422
    assert res2.json()["error"]["code"] == "OVERPAYMENT"


def test_user_notifications_read_and_pagination(
    client_session_provider: tuple[TestClient, Session, MockPaymentProvider, EnvKeyProvider],
) -> None:
    client, _, _, _ = client_session_provider
    alice, bob, group_id = _setup_group_with_debt(client)

    # Check Bob's notifications (he was added to group and has an expense created)
    client.headers["Authorization"] = f"Bearer {bob['api_token']}"
    res_notif = client.get("/users/me/notifications?unread=true")
    assert res_notif.status_code == 200
    notifs = res_notif.json()["items"]
    assert len(notifs) >= 2

    first_notif = notifs[0]
    assert first_notif["read_at"] is None

    # Mark first notification as read
    res_read = client.post(f"/users/me/notifications/{first_notif['id']}/read")
    assert res_read.status_code == 200
    assert res_read.json()["read_at"] is not None

    # Verify unread list excludes the read notification
    res_unread_after = client.get("/users/me/notifications?unread=true")
    assert res_unread_after.status_code == 200
    unread_ids = [n["id"] for n in res_unread_after.json()["items"]]
    assert first_notif["id"] not in unread_ids


def test_dev_mock_provider_pay_simulation(
    client_session_provider: tuple[TestClient, Session, MockPaymentProvider, EnvKeyProvider],
) -> None:
    client, _, _, _ = client_session_provider
    alice, bob, group_id = _setup_group_with_debt(client)

    client.headers["Authorization"] = f"Bearer {bob['api_token']}"
    res_stl = client.post(
        f"/groups/{group_id}/settlements",
        json={
            "from_user": bob["id"],
            "to_user": alice["id"],
            "amount": "500.00",
            "method": "UPI",
        },
    )
    stl = res_stl.json()
    ref = stl["reference"]

    # Use dev helper endpoint to trigger success
    client.headers.pop("Authorization", None)
    res_dev = client.post(f"/dev/mock-provider/pay/{ref}?outcome=success")
    assert res_dev.status_code == 200
    assert res_dev.json()["new_status"] == "SUCCESS"

    # Status updated in database
    client.headers["Authorization"] = f"Bearer {bob['api_token']}"
    res_list = client.get(f"/groups/{group_id}/settlements")
    assert res_list.json()["items"][0]["status"] == "SUCCESS"
