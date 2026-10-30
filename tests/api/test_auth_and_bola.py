"""Comprehensive BOLA and Authentication test suite (OWASP API1 / API2 / API5)."""

import hashlib
from collections.abc import Generator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_db
from app.main import app
from app.repositories import users as users_repo


@pytest.fixture
def auth_client(
    session_factory: sessionmaker,
) -> Generator[tuple[TestClient, Session], None, None]:
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


def _create_user(client: TestClient, name: str) -> tuple[dict[str, Any], str]:
    """Helper to register a user and return (user_data, api_token)."""
    resp = client.post("/users", json={"name": name})
    assert resp.status_code == 201
    data = resp.json()
    return data["user"], data["api_token"]


def test_registration_returns_token_and_hashes_in_db(
    auth_client: tuple[TestClient, Session],
) -> None:
    client, session = auth_client
    resp = client.post("/users", json={"name": "Alice"})
    assert resp.status_code == 201
    data = resp.json()

    assert "user" in data
    assert data["user"]["name"] == "Alice"
    assert data["user"]["id"].startswith("usr_")

    token = data["api_token"]
    assert token.startswith("est_")
    assert len(token) > 40

    # Verify SHA-256 hash in DB
    user = users_repo.get_by_public_id(session, data["user"]["id"])
    assert user is not None
    expected_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    assert user.token_hash == expected_hash


def test_authentication_failures(auth_client: tuple[TestClient, Session]) -> None:
    client, session = auth_client
    alice, token = _create_user(client, "Alice")

    # 1. Missing Authorization header
    resp = client.get("/users")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHENTICATED"

    # 2. Invalid Scheme
    resp = client.get("/users", headers={"Authorization": f"Basic {token}"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHENTICATED"

    # 3. Invalid Token
    resp = client.get("/users", headers={"Authorization": "Bearer est_invalid_token_12345"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHENTICATED"

    # 4. Empty Token
    resp = client.get("/users", headers={"Authorization": "Bearer   "})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHENTICATED"

    # 5. Token hash from database dump cannot authenticate
    user = users_repo.get_by_public_id(session, alice["id"])
    assert user is not None
    resp = client.get("/users", headers={"Authorization": f"Bearer {user.token_hash}"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHENTICATED"


def test_token_rotation(auth_client: tuple[TestClient, Session]) -> None:
    client, session = auth_client
    alice, old_token = _create_user(client, "Alice")

    # Rotate token
    resp = client.post("/users/me/token/rotate", headers={"Authorization": f"Bearer {old_token}"})
    assert resp.status_code == 200
    new_token = resp.json()["api_token"]
    assert new_token != old_token
    assert new_token.startswith("est_")

    # Old token fails with 401
    resp_old = client.get("/users", headers={"Authorization": f"Bearer {old_token}"})
    assert resp_old.status_code == 401
    assert resp_old.json()["error"]["code"] == "UNAUTHENTICATED"

    # New token succeeds
    resp_new = client.get("/users", headers={"Authorization": f"Bearer {new_token}"})
    assert resp_new.status_code == 200


def test_group_creator_is_first_member(auth_client: tuple[TestClient, Session]) -> None:
    client, _ = auth_client
    alice, token = _create_user(client, "Alice")

    # Create group
    resp = client.post(
        "/groups",
        json={"name": "Goa Trip"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    group_id = resp.json()["id"]

    # List members
    members_resp = client.get(
        f"/groups/{group_id}/members",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert members_resp.status_code == 200
    members = members_resp.json()
    assert len(members) == 1
    assert members[0]["user_id"] == alice["id"]
    assert members[0]["name"] == "Alice"


def test_only_members_can_add_members(auth_client: tuple[TestClient, Session]) -> None:
    client, _ = auth_client
    alice, alice_token = _create_user(client, "Alice")
    bob, bob_token = _create_user(client, "Bob")
    charlie, _ = _create_user(client, "Charlie")

    # Alice creates group
    group_resp = client.post(
        "/groups",
        json={"name": "Goa Trip"},
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    group_id = group_resp.json()["id"]

    # Bob (non-member) attempts to add Charlie -> 404 NOT_FOUND
    bob_add_resp = client.post(
        f"/groups/{group_id}/members",
        json={"user_id": charlie["id"]},
        headers={"Authorization": f"Bearer {bob_token}"},
    )
    assert bob_add_resp.status_code == 404
    assert bob_add_resp.json()["error"]["code"] == "NOT_FOUND"

    # Alice (member) adds Bob -> 201
    alice_add_bob = client.post(
        f"/groups/{group_id}/members",
        json={"user_id": bob["id"]},
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    assert alice_add_bob.status_code == 201

    # Now Bob (now member) can add Charlie -> 201
    bob_add_charlie = client.post(
        f"/groups/{group_id}/members",
        json={"user_id": charlie["id"]},
        headers={"Authorization": f"Bearer {bob_token}"},
    )
    assert bob_add_charlie.status_code == 201


@pytest.mark.parametrize(
    "method,endpoint_template,body_template",
    [
        ("GET", "/groups/{group_id}/members", None),
        ("POST", "/groups/{group_id}/members", {"user_id": "{other_user}"}),
        ("GET", "/groups/{group_id}/expenses", None),
        (
            "POST",
            "/groups/{group_id}/expenses",
            {
                "paid_by": "{member_user}",
                "amount": "100.00",
                "description": "Tea",
                "split_type": "EQUAL",
            },
        ),
        ("GET", "/groups/{group_id}/balances", None),
        ("GET", "/groups/{group_id}/settle-up", None),
        ("GET", "/groups/{group_id}/settlements", None),
        (
            "POST",
            "/groups/{group_id}/settlements",
            {"from_user": "{member_user}", "to_user": "{other_user}", "amount": "10.00"},
        ),
    ],
)
def test_bola_non_member_gets_404_on_all_group_routes(
    auth_client: tuple[TestClient, Session],
    method: str,
    endpoint_template: str,
    body_template: dict[str, Any] | None,
) -> None:
    """OWASP API1 (BOLA): Every group-scoped route must return 404 for a non-member,

    with response body identical to querying a completely non-existent group ID.
    """
    client, _ = auth_client
    alice, alice_token = _create_user(client, "Alice")
    bob, _ = _create_user(client, "Bob")
    eve, eve_token = _create_user(client, "Eve")

    # Alice creates group and adds Bob
    group_resp = client.post(
        "/groups",
        json={"name": "Secret Trip"},
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    group_id = group_resp.json()["id"]
    client.post(
        f"/groups/{group_id}/members",
        json={"user_id": bob["id"]},
        headers={"Authorization": f"Bearer {alice_token}"},
    )

    # Prepare endpoint and body
    endpoint = endpoint_template.format(group_id=group_id)
    non_existent_endpoint = endpoint_template.format(group_id="grp_nonexistent99999999")

    json_body = None
    if body_template is not None:
        json_body = {
            k: v.format(member_user=alice["id"], other_user=bob["id"]) if isinstance(v, str) else v
            for k, v in body_template.items()
        }

    # 1. Non-member Eve calls endpoint on real group
    resp_non_member = client.request(
        method=method,
        url=endpoint,
        json=json_body,
        headers={"Authorization": f"Bearer {eve_token}"},
    )
    assert resp_non_member.status_code == 404
    data_non_member = resp_non_member.json()
    assert data_non_member["error"]["code"] == "NOT_FOUND"

    # 2. Eve calls endpoint on non-existent group
    resp_non_existent = client.request(
        method=method,
        url=non_existent_endpoint,
        json=json_body,
        headers={"Authorization": f"Bearer {eve_token}"},
    )
    assert resp_non_existent.status_code == 404
    data_non_existent = resp_non_existent.json()
    assert data_non_existent["error"]["code"] == "NOT_FOUND"

    # 3. Ensure error code and structure match exactly (no info leakage)
    assert data_non_member["error"]["code"] == data_non_existent["error"]["code"]


def test_flat_expense_alias_bola(auth_client: tuple[TestClient, Session]) -> None:
    client, _ = auth_client
    alice, alice_token = _create_user(client, "Alice")
    eve, eve_token = _create_user(client, "Eve")

    group_resp = client.post(
        "/groups",
        json={"name": "Paris Trip"},
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    group_id = group_resp.json()["id"]

    # Eve calls /expenses alias for group she is not a member of
    resp = client.post(
        "/expenses",
        json={
            "group_id": group_id,
            "paid_by": alice["id"],
            "amount": "50.00",
            "description": "Coffee",
            "split_type": "EQUAL",
        },
        headers={"Authorization": f"Bearer {eve_token}"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_users_directory_limited_to_shared_groups(auth_client: tuple[TestClient, Session]) -> None:
    client, _ = auth_client
    alice, alice_token = _create_user(client, "Alice")
    bob, _ = _create_user(client, "Bob")
    charlie, charlie_token = _create_user(client, "Charlie")

    # Alice creates Group A and adds Bob
    g_a = client.post(
        "/groups", json={"name": "Group A"}, headers={"Authorization": f"Bearer {alice_token}"}
    ).json()["id"]
    client.post(
        f"/groups/{g_a}/members",
        json={"user_id": bob["id"]},
        headers={"Authorization": f"Bearer {alice_token}"},
    )

    # Charlie creates Group B (Alice and Bob are NOT in Group B)
    client.post(
        "/groups", json={"name": "Group B"}, headers={"Authorization": f"Bearer {charlie_token}"}
    )

    # Alice lists users -> sees only herself and Bob
    alice_users_resp = client.get("/users", headers={"Authorization": f"Bearer {alice_token}"})
    assert alice_users_resp.status_code == 200
    alice_user_ids = {u["id"] for u in alice_users_resp.json()["items"]}
    assert alice["id"] in alice_user_ids
    assert bob["id"] in alice_user_ids
    assert charlie["id"] not in alice_user_ids

    # Charlie lists users -> sees only Charlie
    charlie_users_resp = client.get("/users", headers={"Authorization": f"Bearer {charlie_token}"})
    assert charlie_users_resp.status_code == 200
    charlie_user_ids = {u["id"] for u in charlie_users_resp.json()["items"]}
    assert charlie["id"] in charlie_user_ids
    assert alice["id"] not in charlie_user_ids
    assert bob["id"] not in charlie_user_ids


def test_balances_limited_to_actor_groups(auth_client: tuple[TestClient, Session]) -> None:
    client, _ = auth_client
    alice, alice_token = _create_user(client, "Alice")
    charlie, charlie_token = _create_user(client, "Charlie")

    # Alice creates Group 1
    g1 = client.post(
        "/groups", json={"name": "Group 1"}, headers={"Authorization": f"Bearer {alice_token}"}
    ).json()["id"]
    # Charlie creates Group 2
    g2 = client.post(
        "/groups", json={"name": "Group 2"}, headers={"Authorization": f"Bearer {charlie_token}"}
    ).json()["id"]

    # Alice calls /balances -> sees only Group 1
    alice_bal_resp = client.get("/balances", headers={"Authorization": f"Bearer {alice_token}"})
    assert alice_bal_resp.status_code == 200
    alice_group_ids = [item["group"]["id"] for item in alice_bal_resp.json()["groups"]]
    assert g1 in alice_group_ids
    assert g2 not in alice_group_ids
