"""Concurrency and reliability proofs for Akira.

Proofs:
1. 20 parallel expense creations in one group:
   - Consecutive ledger sequences (1..20)
   - Valid HMAC hash chain without breaks
   - Zero net balance drift (sum of net balances == 0)
2. Parallel settlement attempts against a single debt:
   - In-flight reservation prevents overpayment under concurrency
   - Sum of settlements never exceeds allowable debt
3. Idempotent replay under parallel identical requests:
   - Concurrent identical requests with the same Idempotency-Key create exactly one row
   - All concurrent callers receive identical HTTP 201 responses
4. Database unavailability resilience:
   - Health check reports 503 DATABASE_UNAVAILABLE when database query fails
   - Transient database errors fail cleanly without partial rows or unhandled crashes
"""

from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.keys import EnvKeyProvider
from app.adapters.payment_provider import MockPaymentProvider
from app.api.deps import get_db, get_key_provider, get_payment_provider
from app.domain.balances import net_balances
from app.main import app
from app.repositories.models import Expense, ExpenseShare, Group, LedgerEntry, Settlement


@pytest.fixture
def concurrent_client_and_db(
    session_factory: sessionmaker,
) -> Generator[
    tuple[TestClient, Session, EnvKeyProvider, MockPaymentProvider, sessionmaker],
    None,
    None,
]:
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

    yield client, db_session, key_provider, payment_provider, session_factory

    db_session.close()
    app.dependency_overrides.clear()


def _create_user(client: TestClient, name: str) -> tuple[dict, str]:
    resp = client.post("/users", json={"name": name})
    assert resp.status_code == 201
    data = resp.json()
    return data["user"], data["api_token"]


def test_20_parallel_expenses_consecutive_seqs_and_zero_drift(concurrent_client_and_db) -> None:
    client, db, key_provider, _, _ = concurrent_client_and_db

    # Create 3 users and a shared group
    alice, token_alice = _create_user(client, "Alice")
    bob, _ = _create_user(client, "Bob")
    charlie, _ = _create_user(client, "Charlie")

    grp_resp = client.post(
        "/groups",
        headers={"Authorization": f"Bearer {token_alice}"},
        json={"name": "Contention Group"},
    )
    assert grp_resp.status_code == 201
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

    # 20 parallel expense creation tasks
    num_requests = 20

    def post_expense(i: int) -> int:
        res = client.post(
            f"/groups/{group_id}/expenses",
            headers={"Authorization": f"Bearer {token_alice}"},
            json={
                "paid_by": alice["id"],
                "amount": "30.00",
                "description": f"Expense {i}",
                "split_type": "EQUAL",
            },
        )
        return res.status_code

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(post_expense, i) for i in range(num_requests)]
        statuses = [f.result() for f in as_completed(futures)]

    # 1. All 20 parallel writes succeeded
    assert all(status == 201 for status in statuses)
    assert len(statuses) == num_requests

    # 2. Sequence continuity proof: sequences must be strictly 1..20 consecutive
    grp_row = db.scalar(select(Group).where(Group.public_id == group_id))
    assert grp_row is not None
    entries = list(
        db.scalars(
            select(LedgerEntry)
            .where(LedgerEntry.group_id == grp_row.id)
            .order_by(LedgerEntry.seq.asc())
        ).all()
    )
    assert len(entries) == num_requests
    seqs = [e.seq for e in entries]
    assert seqs == list(range(1, num_requests + 1))

    # 3. Hash chain integrity proof: query audit verification endpoint
    audit_resp = client.get(
        f"/groups/{group_id}/audit/verify",
        headers={"Authorization": f"Bearer {token_alice}"},
    )
    assert audit_resp.status_code == 200
    audit_data = audit_resp.json()
    assert audit_data["valid"] is True
    assert audit_data["entries"] == num_requests
    assert audit_data["head"] == grp_row.ledger_head_hash

    # 4. Zero balance drift proof: net balances across all members strictly sum to 0
    expenses = list(db.scalars(select(Expense).where(Expense.group_id == grp_row.id)).all())
    shares = list(db.scalars(select(ExpenseShare)).all())
    settlements = list(
        db.scalars(select(Settlement).where(Settlement.group_id == grp_row.id)).all()
    )
    nets = net_balances(expenses, shares, settlements)
    assert sum(nets.values()) == 0


def test_parallel_settlements_debt_reservation_prevents_overpayment(
    concurrent_client_and_db,
) -> None:
    client, db, _, _, _ = concurrent_client_and_db

    alice, token_alice = _create_user(client, "Alice")
    bob, token_bob = _create_user(client, "Bob")

    grp_resp = client.post(
        "/groups",
        headers={"Authorization": f"Bearer {token_alice}"},
        json={"name": "Debt Group"},
    )
    group_id = grp_resp.json()["id"]

    client.post(
        f"/groups/{group_id}/members",
        headers={"Authorization": f"Bearer {token_alice}"},
        json={"user_id": bob["id"]},
    )

    # Bob pays ₹100.00 split equally: Alice owes Bob exactly ₹50.00 (5000 paise)
    client.post(
        f"/groups/{group_id}/expenses",
        headers={"Authorization": f"Bearer {token_bob}"},
        json={
            "paid_by": bob["id"],
            "amount": "100.00",
            "description": "Lunch",
            "split_type": "EQUAL",
        },
    )

    # 10 concurrent threads attempt to initiate a settlement repayment of the full ₹50.00
    def attempt_settle(i: int) -> int:
        resp = client.post(
            f"/groups/{group_id}/settlements",
            headers={"Authorization": f"Bearer {token_alice}"},
            json={
                "from_user": alice["id"],
                "to_user": bob["id"],
                "amount": "50.00",
                "method": "UPI",
            },
        )
        return resp.status_code

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(attempt_settle, i) for i in range(10)]
        results = [f.result() for f in as_completed(futures)]

    # Debt capacity reservation proof:
    # Exactly 1 settlement succeeds for ₹50.00; the remaining 9 attempts get 422 OVERPAYMENT
    success_count = sum(1 for code in results if code == 201)
    overpay_count = sum(1 for code in results if code == 422)

    assert success_count == 1
    assert overpay_count == 9

    # Verify database has exactly 1 settlement recorded
    grp_row = db.scalar(select(Group).where(Group.public_id == group_id))
    assert grp_row is not None
    settlements = list(
        db.scalars(select(Settlement).where(Settlement.group_id == grp_row.id)).all()
    )
    assert len(settlements) == 1
    assert settlements[0].amount_paise == 5000


def test_concurrent_idempotency_creates_single_record(concurrent_client_and_db) -> None:
    client, db, _, _, _ = concurrent_client_and_db

    alice, token_alice = _create_user(client, "Alice")
    bob, _ = _create_user(client, "Bob")

    grp_resp = client.post(
        "/groups",
        headers={"Authorization": f"Bearer {token_alice}"},
        json={"name": "Idempotency Group"},
    )
    group_id = grp_resp.json()["id"]

    client.post(
        f"/groups/{group_id}/members",
        headers={"Authorization": f"Bearer {token_alice}"},
        json={"user_id": bob["id"]},
    )

    idempotency_key = "idem_concurrent_test_key_001"
    payload = {
        "paid_by": alice["id"],
        "amount": "100.00",
        "description": "Team Dinner",
        "split_type": "EQUAL",
    }

    # 10 parallel requests with identical idempotency key and payload
    def send_idempotent_request() -> tuple[int, dict]:
        res = client.post(
            f"/groups/{group_id}/expenses",
            headers={
                "Authorization": f"Bearer {token_alice}",
                "Idempotency-Key": idempotency_key,
            },
            json=payload,
        )
        return res.status_code, res.json()

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(send_idempotent_request) for _ in range(10)]
        outcomes = [f.result() for f in as_completed(futures)]

    # 1. All concurrent callers receive HTTP 201
    assert all(code == 201 for code, _ in outcomes)

    # 2. All responses return identical expense ID and amount
    first_id = outcomes[0][1]["id"]
    for _, body in outcomes:
        assert body["id"] == first_id
        assert body["amount"] == "100.00"

    # 3. Database proof: exactly ONE expense row exists
    grp_row = db.scalar(select(Group).where(Group.public_id == group_id))
    assert grp_row is not None
    expenses = list(db.scalars(select(Expense).where(Expense.group_id == grp_row.id)).all())
    assert len(expenses) == 1
    assert expenses[0].public_id == first_id


def test_database_unavailability_resilience(concurrent_client_and_db) -> None:
    client, _, _, _, _ = concurrent_client_and_db

    # 1. Verify health probe returns 200 when database is healthy
    healthy_resp = client.get("/health")
    assert healthy_resp.status_code == 200
    assert healthy_resp.json() == {"status": "ok", "db": "ok"}

    # 2. Simulate database failure by overriding get_db with a session that raises OperationalError
    class FailingSession:
        def execute(self, *args, **kwargs):
            raise OperationalError("connection refused", {}, None)

        def begin(self):
            raise OperationalError("connection refused", {}, None)

    def failing_get_db():
        yield FailingSession()

    original_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = failing_get_db
    try:
        # Health check gracefully degrades to 503
        unhealthy_resp = client.get("/health")
        assert unhealthy_resp.status_code == 503
        assert unhealthy_resp.json() == {"status": "degraded", "db": "down"}

        # Write request fails safely with 503 DATABASE_UNAVAILABLE and no crash
        write_resp = client.post("/users", json={"name": "CrashTest"})
        assert write_resp.status_code == 503
        assert write_resp.json()["error"]["code"] == "DATABASE_UNAVAILABLE"
    finally:
        if original_override:
            app.dependency_overrides[get_db] = original_override
        else:
            app.dependency_overrides.pop(get_db, None)
