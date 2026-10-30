"""API tests for Balances, Settle-up suggestions, and Recorded Settlements."""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.db import Base
from app.main import app


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


def _setup_group(
    client: TestClient, group_name: str, member_names: list[str]
) -> tuple[str, list[dict]]:
    users = []
    for name in member_names:
        u_res = client.post("/users", json={"name": name})
        assert u_res.status_code == 201
        u_data = u_res.json()
        users.append(u_data)

    creator = users[0]
    client.headers["Authorization"] = f"Bearer {creator['api_token']}"
    g_res = client.post("/groups", json={"name": group_name})
    assert g_res.status_code == 201
    group_id = g_res.json()["id"]

    for u_data in users[1:]:
        m_res = client.post(f"/groups/{group_id}/members", json={"user_id": u_data["id"]})
        assert m_res.status_code == 201

    return group_id, users


def test_brief_example_balances(client_and_session: tuple[TestClient, Session]) -> None:
    client, _ = client_and_session
    # Mohit, Rahul, Ankit
    group_id, users = _setup_group(client, "Goa Trip", ["Mohit", "Rahul", "Ankit"])
    mohit, _, _ = users[0], users[1], users[2]

    # Mohit pays 1200 equal split
    res = client.post(
        f"/groups/{group_id}/expenses",
        json={
            "paid_by": mohit["id"],
            "amount": "1200",
            "description": "Lunch at Fisherman's Wharf",
            "split_type": "EQUAL",
        },
    )
    assert res.status_code == 201

    # Check balances
    bal_res = client.get(f"/groups/{group_id}/balances")
    assert bal_res.status_code == 200
    data = bal_res.json()

    # Exact brief shape in `balances`
    expected_balances = {
        "Rahul": {"owes": {"Mohit": "400.00"}},
        "Ankit": {"owes": {"Mohit": "400.00"}},
    }
    assert data["balances"] == expected_balances

    # Net balances
    net_by_name = {item["user"]["name"]: item["net"] for item in data["net"]}
    assert net_by_name["Mohit"] == "800.00"
    assert net_by_name["Rahul"] == "-400.00"
    assert net_by_name["Ankit"] == "-400.00"

    # Invariant: sum of net balances is zero
    total_net = sum(Decimal(item["net"]) for item in data["net"])
    assert total_net == Decimal("0.00")


def test_repayment_and_overpayment_error(client_and_session: tuple[TestClient, Session]) -> None:
    client, _ = client_and_session
    group_id, users = _setup_group(client, "Goa Trip", ["Mohit", "Rahul", "Ankit"])
    mohit, rahul, _ = users[0], users[1], users[2]

    # Mohit pays 1200
    client.post(
        f"/groups/{group_id}/expenses",
        json={
            "paid_by": mohit["id"],
            "amount": "1200",
            "description": "Dinner",
            "split_type": "EQUAL",
        },
    )

    # Rahul owes Mohit 400. Rahul tries to overpay 450 -> 422 OVERPAYMENT
    overpay_res = client.post(
        f"/groups/{group_id}/settlements",
        json={
            "from_user": rahul["id"],
            "to_user": mohit["id"],
            "amount": "450.00",
            "method": "CASH",
        },
    )
    assert overpay_res.status_code == 422
    assert overpay_res.json()["error"]["code"] == "OVERPAYMENT"

    # Rahul pays Mohit exactly 400.00 -> 201 Created
    settle_res = client.post(
        f"/groups/{group_id}/settlements",
        json={
            "from_user": rahul["id"],
            "to_user": mohit["id"],
            "amount": "400.00",
            "method": "CASH",
        },
    )
    assert settle_res.status_code == 201
    stl_data = settle_res.json()
    assert stl_data["id"].startswith("stl_")
    assert stl_data["status"] == "CONFIRMED"

    # Rahul disappears from balances
    bal_res = client.get(f"/groups/{group_id}/balances")
    data = bal_res.json()
    assert "Rahul" not in data["balances"]
    assert data["balances"] == {"Ankit": {"owes": {"Mohit": "400.00"}}}

    # Rahul's net is now 0.00, Mohit's is 400.00, Ankit's is -400.00
    net_by_name = {item["user"]["name"]: item["net"] for item in data["net"]}
    assert net_by_name["Rahul"] == "0.00"
    assert net_by_name["Mohit"] == "400.00"
    assert net_by_name["Ankit"] == "-400.00"


def test_settle_up_suggestions_zero_nets(client_and_session: tuple[TestClient, Session]) -> None:
    client, _ = client_and_session
    group_id, users = _setup_group(client, "Goa Trip", ["Alice", "Bob", "Charlie", "David"])
    u1, u2, u3, _ = users[0], users[1], users[2], users[3]

    # Alice pays 1000
    client.post(
        f"/groups/{group_id}/expenses",
        json={"paid_by": u1["id"], "amount": "1000", "description": "Villa", "split_type": "EQUAL"},
    )
    # Bob pays 600
    client.post(
        f"/groups/{group_id}/expenses",
        json={
            "paid_by": u2["id"],
            "amount": "600",
            "description": "Groceries",
            "split_type": "EQUAL",
        },
    )
    # Charlie pays 200
    client.post(
        f"/groups/{group_id}/expenses",
        json={"paid_by": u3["id"], "amount": "200", "description": "Drinks", "split_type": "EQUAL"},
    )

    # Get settle-up suggestions
    res = client.get(f"/groups/{group_id}/settle-up")
    assert res.status_code == 200
    settle_data = res.json()
    transfers = settle_data["transfers"]
    assert len(transfers) <= 3  # at most n - 1 = 3 transfers

    # Execute all suggested transfers
    for t in transfers:
        stl_res = client.post(
            f"/groups/{group_id}/settlements",
            json={
                "from_user": t["from"]["id"],
                "to_user": t["to"]["id"],
                "amount": t["amount"],
                "method": "OTHER",
            },
        )
        assert stl_res.status_code == 201

    # Balances should now be completely settled: all net balances zero
    final_bal = client.get(f"/groups/{group_id}/balances").json()
    for item in final_bal["net"]:
        assert item["net"] == "0.00"


def test_six_users_transfers_bound(client_and_session: tuple[TestClient, Session]) -> None:
    client, _ = client_and_session
    names = ["U1", "U2", "U3", "U4", "U5", "U6"]
    group_id, users = _setup_group(client, "Big Trip", names)

    # Mixed expenses
    client.post(
        f"/groups/{group_id}/expenses",
        json={
            "paid_by": users[0]["id"],
            "amount": "1200",
            "description": "E1",
            "split_type": "EQUAL",
        },
    )
    client.post(
        f"/groups/{group_id}/expenses",
        json={
            "paid_by": users[1]["id"],
            "amount": "600",
            "description": "E2",
            "split_type": "EQUAL",
        },
    )
    client.post(
        f"/groups/{group_id}/expenses",
        json={
            "paid_by": users[2]["id"],
            "amount": "300",
            "description": "E3",
            "split_type": "EQUAL",
        },
    )

    res = client.get(f"/groups/{group_id}/settle-up")
    assert res.status_code == 200
    data = res.json()
    # At most 6 - 1 = 5 transfers
    assert data["count"] <= 5
    assert len(data["transfers"]) <= 5


def test_get_all_balances_alias(client_and_session: tuple[TestClient, Session]) -> None:
    client, _ = client_and_session
    g1, u_g1 = _setup_group(client, "Trip 1", ["A", "B"])

    # Record expense in Trip 1 while authenticated as A
    client.post(
        f"/groups/{g1}/expenses",
        json={
            "paid_by": u_g1[0]["id"],
            "amount": "200",
            "description": "Taxi",
            "split_type": "EQUAL",
        },
    )

    g2, u_g2 = _setup_group(client, "Trip 2", ["C", "D"])

    # Add A to Trip 2 so A is a member of both groups
    client.post(f"/groups/{g2}/members", json={"user_id": u_g1[0]["id"]})

    client.post(
        f"/groups/{g2}/expenses",
        json={
            "paid_by": u_g2[0]["id"],
            "amount": "400",
            "description": "Hotel",
            "split_type": "EQUAL",
        },
    )

    # Authenticate as A (member of both Trip 1 and Trip 2)
    client.headers["Authorization"] = f"Bearer {u_g1[0]['api_token']}"
    res = client.get("/balances")
    assert res.status_code == 200
    data = res.json()
    assert "groups" in data
    assert len(data["groups"]) >= 2
    group_ids = [item["group"]["id"] for item in data["groups"]]
    assert g1 in group_ids
    assert g2 in group_ids


def test_settlements_pagination(client_and_session: tuple[TestClient, Session]) -> None:
    client, _ = client_and_session
    group_id, users = _setup_group(client, "Trip", ["Debtor", "Creditor"])
    d, c = users[0], users[1]

    # Creditor pays 1000
    client.post(
        f"/groups/{group_id}/expenses",
        json={"paid_by": c["id"], "amount": "1000", "description": "Tour", "split_type": "EQUAL"},
    )
    # Debtor owes 500. Debtor makes 5 partial payments of 100 each
    for _ in range(5):
        res = client.post(
            f"/groups/{group_id}/settlements",
            json={
                "from_user": d["id"],
                "to_user": c["id"],
                "amount": "100.00",
                "method": "CASH",
            },
        )
        assert res.status_code == 201

    # Page 1: limit=2
    res1 = client.get(f"/groups/{group_id}/settlements?limit=2")
    assert res1.status_code == 200
    p1 = res1.json()
    assert len(p1["items"]) == 2
    assert p1["next_cursor"] is not None

    # Page 2: limit=2
    res2 = client.get(f"/groups/{group_id}/settlements?limit=2&cursor={p1['next_cursor']}")
    assert res2.status_code == 200
    p2 = res2.json()
    assert len(p2["items"]) == 2
    assert p2["next_cursor"] is not None

    # Page 3: limit=2
    res3 = client.get(f"/groups/{group_id}/settlements?limit=2&cursor={p2['next_cursor']}")
    assert res3.status_code == 200
    p3 = res3.json()
    assert len(p3["items"]) == 1
    assert p3["next_cursor"] is None
