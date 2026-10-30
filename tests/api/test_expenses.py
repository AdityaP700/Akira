"""API tests for atomic, locked, idempotent expense creation and listing."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.db import Base
from app.main import app
from app.repositories.models import Expense, ExpenseShare, LedgerEntry


@pytest.fixture
def client_and_session() -> tuple[TestClient, Session]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    test_session = session_factory()
    try:
        yield client, test_session
    finally:
        test_session.close()
        app.dependency_overrides.clear()


def _setup_group_with_members(
    client: TestClient, member_names: list[str]
) -> tuple[str, list[dict]]:
    # Create group
    g_res = client.post("/groups", json={"name": "Goa Trip"})
    assert g_res.status_code == 201
    group_id = g_res.json()["id"]

    users = []
    for name in member_names:
        u_res = client.post("/users", json={"name": name})
        assert u_res.status_code == 201
        u_data = u_res.json()
        users.append(u_data)
        # Add to group
        m_res = client.post(f"/groups/{group_id}/members", json={"user_id": u_data["id"]})
        assert m_res.status_code == 201

    return group_id, users


def test_brief_example_equal_split(client_and_session: tuple[TestClient, Session]) -> None:
    client, session = client_and_session
    group_id, users = _setup_group_with_members(client, ["Alice", "Bob", "Charlie"])

    payload = {
        "paid_by": users[0]["id"],
        "amount": "1200",
        "description": "Dinner at Fisherman's Wharf",
        "split_type": "EQUAL",
    }
    res = client.post(f"/groups/{group_id}/expenses", json=payload)
    assert res.status_code == 201
    data = res.json()

    assert data["id"].startswith("exp_")
    assert data["amount"] == "1200.00"
    assert data["paid_by"]["id"] == users[0]["id"]
    assert len(data["shares"]) == 3
    for share in data["shares"]:
        assert share["amount"] == "400.00"

    # Verify ledger entry was created
    ledger = list(session.scalars(select(LedgerEntry)).all())
    assert len(ledger) == 1
    assert ledger[0].entry_type == "EXPENSE"
    assert ledger[0].payload["amount_paise"] == 120000


def test_equal_split_remainder_deterministic(
    client_and_session: tuple[TestClient, Session],
) -> None:
    client, _ = client_and_session
    group_id, users = _setup_group_with_members(client, ["Alice", "Bob", "Charlie"])

    # 1000 / 3 = 333.33 with 1 paise remainder -> lowest user id gets 333.34
    payload = {
        "paid_by": users[0]["id"],
        "amount": "1000",
        "description": "Scuba Diving",
        "split_type": "EQUAL",
    }
    res = client.post(f"/groups/{group_id}/expenses", json=payload)
    assert res.status_code == 201
    data = res.json()

    # User IDs in shares are sorted ascending by public id
    amounts = sorted([s["amount"] for s in data["shares"]], reverse=True)
    assert amounts == ["333.34", "333.33", "333.33"]


def test_exact_split_success_and_errors(client_and_session: tuple[TestClient, Session]) -> None:
    client, _ = client_and_session
    group_id, users = _setup_group_with_members(client, ["Alice", "Bob"])

    # Success: 400 + 600 = 1000
    exact_payload = {
        "paid_by": users[0]["id"],
        "amount": "1000",
        "description": "Fuel",
        "split_type": "EXACT",
        "splits": [
            {"user_id": users[0]["id"], "amount": "400.00"},
            {"user_id": users[1]["id"], "amount": "600.00"},
        ],
    }
    res = client.post(f"/groups/{group_id}/expenses", json=exact_payload)
    assert res.status_code == 201

    # Error: Mismatch sum (300 + 600 = 900 != 1000)
    bad_sum_payload = dict(exact_payload)
    bad_sum_payload["splits"] = [
        {"user_id": users[0]["id"], "amount": "300.00"},
        {"user_id": users[1]["id"], "amount": "600.00"},
    ]
    res_bad = client.post(f"/groups/{group_id}/expenses", json=bad_sum_payload)
    assert res_bad.status_code == 422
    assert res_bad.json()["error"]["code"] == "VALIDATION_ERROR"

    # Error: Participant not in group
    u_outsider = client.post("/users", json={"name": "Outsider"}).json()
    bad_member_payload = dict(exact_payload)
    bad_member_payload["splits"] = [
        {"user_id": users[0]["id"], "amount": "400.00"},
        {"user_id": u_outsider["id"], "amount": "600.00"},
    ]
    res_non_member = client.post(f"/groups/{group_id}/expenses", json=bad_member_payload)
    assert res_non_member.status_code == 422
    assert res_non_member.json()["error"]["code"] == "PARTICIPANT_NOT_MEMBER"


def test_invalid_amounts(client_and_session: tuple[TestClient, Session]) -> None:
    client, _ = client_and_session
    group_id, users = _setup_group_with_members(client, ["Alice", "Bob"])

    for invalid_amt in ["0", "-5", "abc", "10.001", "10000001"]:
        payload = {
            "paid_by": users[0]["id"],
            "amount": invalid_amt,
            "description": "Test",
            "split_type": "EQUAL",
        }
        res = client.post(f"/groups/{group_id}/expenses", json=payload)
        assert res.status_code == 422


def test_member_added_after_expense(client_and_session: tuple[TestClient, Session]) -> None:
    client, _ = client_and_session
    group_id, users = _setup_group_with_members(client, ["Alice", "Bob"])

    # Expense 1 with Alice and Bob
    res1 = client.post(
        f"/groups/{group_id}/expenses",
        json={
            "paid_by": users[0]["id"],
            "amount": "100",
            "description": "Breakfast",
            "split_type": "EQUAL",
        },
    )
    assert res1.status_code == 201
    exp1_users = {s["user_id"] for s in res1.json()["shares"]}
    assert len(exp1_users) == 2

    # Add Charlie
    u3 = client.post("/users", json={"name": "Charlie"}).json()
    client.post(f"/groups/{group_id}/members", json={"user_id": u3["id"]})

    # Expense 2 with Alice, Bob, and Charlie
    res2 = client.post(
        f"/groups/{group_id}/expenses",
        json={
            "paid_by": users[0]["id"],
            "amount": "150",
            "description": "Lunch",
            "split_type": "EQUAL",
        },
    )
    assert res2.status_code == 201
    exp2_users = {s["user_id"] for s in res2.json()["shares"]}
    assert len(exp2_users) == 3
    assert u3["id"] not in exp1_users
    assert u3["id"] in exp2_users


def test_idempotency_key_replay_and_conflict(
    client_and_session: tuple[TestClient, Session],
) -> None:
    client, session = client_and_session
    group_id, users = _setup_group_with_members(client, ["Alice", "Bob"])

    headers = {"Idempotency-Key": "req_key_12345"}
    payload = {
        "paid_by": users[0]["id"],
        "amount": "500",
        "description": "Snacks",
        "split_type": "EQUAL",
    }

    # First request
    res1 = client.post(f"/groups/{group_id}/expenses", json=payload, headers=headers)
    assert res1.status_code == 201
    data1 = res1.json()

    # Second request with SAME body -> returns identical response
    res2 = client.post(f"/groups/{group_id}/expenses", json=payload, headers=headers)
    assert res2.status_code == 201
    data2 = res2.json()
    assert data1["id"] == data2["id"]
    assert data1["amount"] == data2["amount"]

    # Verify only ONE expense and ONE ledger row created
    expenses = list(session.scalars(select(Expense)).all())
    assert len(expenses) == 1

    # Third request with SAME key + DIFFERENT body -> 422 IDEMPOTENCY_KEY_REUSED
    diff_payload = dict(payload)
    diff_payload["amount"] = "600"
    res3 = client.post(f"/groups/{group_id}/expenses", json=diff_payload, headers=headers)
    assert res3.status_code == 422
    assert res3.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"


def test_single_member_warning(client_and_session: tuple[TestClient, Session]) -> None:
    client, _ = client_and_session
    group_id, users = _setup_group_with_members(client, ["Solo"])

    payload = {
        "paid_by": users[0]["id"],
        "amount": "200",
        "description": "Solo coffee",
        "split_type": "EQUAL",
    }
    res = client.post(f"/groups/{group_id}/expenses", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["warning"] == "NO_OTHER_PARTICIPANTS"
    assert len(data["shares"]) == 1
    assert data["shares"][0]["amount"] == "200.00"


def test_post_expenses_alias(client_and_session: tuple[TestClient, Session]) -> None:
    client, _ = client_and_session
    group_id, users = _setup_group_with_members(client, ["Alice", "Bob"])

    payload = {
        "group_id": group_id,
        "paid_by": users[0]["id"],
        "amount": "300",
        "description": "Taxi",
        "split_type": "EQUAL",
    }
    res = client.post("/expenses", json=payload)
    assert res.status_code == 201
    assert res.json()["amount"] == "300.00"

    # Missing group_id in alias body
    bad_payload = dict(payload)
    del bad_payload["group_id"]
    res_bad = client.post("/expenses", json=bad_payload)
    assert res_bad.status_code == 422


def test_crash_simulation_rollback(client_and_session: tuple[TestClient, Session]) -> None:
    client, session = client_and_session
    group_id, users = _setup_group_with_members(client, ["Alice", "Bob"])

    payload = {
        "paid_by": users[0]["id"],
        "amount": "800",
        "description": "Parasailing",
        "split_type": "EQUAL",
    }

    # Simulate crash during ledger append
    with patch(
        "app.repositories.ledger.append", side_effect=RuntimeError("Simulated ledger failure")
    ):
        with pytest.raises(RuntimeError, match="Simulated ledger failure"):
            client.post(f"/groups/{group_id}/expenses", json=payload)

    # Verify no expense or share rows exist
    expenses = list(session.scalars(select(Expense)).all())
    shares = list(session.scalars(select(ExpenseShare)).all())
    assert len(expenses) == 0
    assert len(shares) == 0


def test_list_group_expenses_pagination(client_and_session: tuple[TestClient, Session]) -> None:
    client, _ = client_and_session
    group_id, users = _setup_group_with_members(client, ["Alice", "Bob"])

    # Create 5 expenses
    for i in range(5):
        client.post(
            f"/groups/{group_id}/expenses",
            json={
                "paid_by": users[0]["id"],
                "amount": f"{100 + i * 10}",
                "description": f"Expense_{i}",
                "split_type": "EQUAL",
            },
        )

    # Page 1: limit=2
    res1 = client.get(f"/groups/{group_id}/expenses?limit=2")
    assert res1.status_code == 200
    page1 = res1.json()
    assert len(page1["items"]) == 2
    assert page1["next_cursor"] is not None

    # Page 2: limit=2
    res2 = client.get(f"/groups/{group_id}/expenses?limit=2&cursor={page1['next_cursor']}")
    assert res2.status_code == 200
    page2 = res2.json()
    assert len(page2["items"]) == 2
    assert page2["next_cursor"] is not None

    # Page 3: limit=2
    res3 = client.get(f"/groups/{group_id}/expenses?limit=2&cursor={page2['next_cursor']}")
    assert res3.status_code == 200
    page3 = res3.json()
    assert len(page3["items"]) == 1
    assert page3["next_cursor"] is None
