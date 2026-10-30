"""API tests for Users, Groups, and Membership endpoints."""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_db
from app.main import app


@pytest.fixture
def client_and_session(
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

    # Setup default authenticated actor for baseline tests
    res = client.post("/users", json={"name": "Setup Actor"})
    token = res.json()["api_token"]
    client.headers["Authorization"] = f"Bearer {token}"

    test_session = session_factory()
    try:
        yield client, test_session
    finally:
        test_session.close()
        app.dependency_overrides.clear()


def test_create_user_happy_path(client_and_session: tuple[TestClient, Session]) -> None:
    client, _ = client_and_session
    response = client.post("/users", json={"name": "Mohit"})
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Mohit"
    assert data["id"].startswith("usr_")
    assert "created_at" in data
    assert "api_token" in data


def test_create_user_validation_errors(client_and_session: tuple[TestClient, Session]) -> None:
    client, _ = client_and_session

    # Empty name
    res = client.post("/users", json={"name": ""})
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"

    # Spaces only
    res = client.post("/users", json={"name": "   "})
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"

    # Extra forbidden field
    res = client.post("/users", json={"name": "Mohit", "role": "admin"})
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"


def test_users_pagination(client_and_session: tuple[TestClient, Session]) -> None:
    client, _ = client_and_session

    # Create a group so all created users share a group with the caller
    g_res = client.post("/groups", json={"name": "Pagination Group"})
    group_id = g_res.json()["id"]

    # Create 25 users and add them to group
    created_ids = []
    for i in range(25):
        res = client.post("/users", json={"name": f"User_{i:02d}"})
        assert res.status_code == 201
        uid = res.json()["id"]
        created_ids.append(uid)
        client.post(f"/groups/{group_id}/members", json={"user_id": uid})

    # Page 1: limit=10
    res1 = client.get("/users?limit=10")
    assert res1.status_code == 200
    page1 = res1.json()
    assert len(page1["items"]) == 10
    assert page1["next_cursor"] is not None

    # Page 2: limit=10 using cursor
    res2 = client.get(f"/users?limit=10&cursor={page1['next_cursor']}")
    assert res2.status_code == 200
    page2 = res2.json()
    assert len(page2["items"]) == 10
    assert page2["next_cursor"] is not None

    # Page 3: limit=10 (remaining items: 25 created + 1 Setup Actor = 26 total items)
    res3 = client.get(f"/users?limit=10&cursor={page2['next_cursor']}")
    assert res3.status_code == 200
    page3 = res3.json()
    assert len(page3["items"]) == 6
    assert page3["next_cursor"] is None

    # Verify all created items returned exactly once
    all_returned_ids = (
        [u["id"] for u in page1["items"]]
        + [u["id"] for u in page2["items"]]
        + [u["id"] for u in page3["items"]]
    )
    assert len(all_returned_ids) == 26
    assert len(set(all_returned_ids)) == 26
    for cid in created_ids:
        assert cid in all_returned_ids

    # Bad cursor -> 422
    res_bad = client.get("/users?cursor=invalid_garbage_base64_or_data")
    assert res_bad.status_code == 422
    assert res_bad.json()["error"]["code"] == "VALIDATION_ERROR"


def test_create_group_happy_path(client_and_session: tuple[TestClient, Session]) -> None:
    client, _ = client_and_session
    response = client.post("/groups", json={"name": "Goa Trip"})
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Goa Trip"
    assert data["id"].startswith("grp_")
    assert "created_at" in data


def test_create_group_validation_errors(client_and_session: tuple[TestClient, Session]) -> None:
    client, _ = client_and_session

    res = client.post("/groups", json={"name": "   "})
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"

    res = client.post("/groups", json={"name": "Goa Trip", "extra": "forbidden"})
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"


def test_add_and_list_group_members(client_and_session: tuple[TestClient, Session]) -> None:
    client, _ = client_and_session

    u1 = client.post("/users", json={"name": "Mohit"}).json()
    u2 = client.post("/users", json={"name": "Rahul"}).json()

    # Mohit creates Flatmates group using his own token
    client.headers["Authorization"] = f"Bearer {u1['api_token']}"
    g = client.post("/groups", json={"name": "Flatmates"}).json()

    # Mohit adds Rahul
    res = client.post(f"/groups/{g['id']}/members", json={"user_id": u2["id"]})
    assert res.status_code == 201
    data = res.json()
    assert data["group_id"] == g["id"]
    assert data["user_id"] == u2["id"]
    assert data["name"] == "Rahul"
    assert "joined_at" in data

    # Duplicate member -> 409 ALREADY_MEMBER
    dup = client.post(f"/groups/{g['id']}/members", json={"user_id": u2["id"]})
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "ALREADY_MEMBER"

    # List members -> Mohit (creator) + Rahul = 2
    members_res = client.get(f"/groups/{g['id']}/members")
    assert members_res.status_code == 200
    members = members_res.json()
    assert len(members) == 2
    assert {m["user_id"] for m in members} == {u1["id"], u2["id"]}


def test_group_and_member_404_cases(client_and_session: tuple[TestClient, Session]) -> None:
    client, _ = client_and_session

    u = client.post("/users", json={"name": "Mohit"}).json()

    # Add member to non-existent group -> 404
    res = client.post("/groups/grp_nonexistent/members", json={"user_id": u["id"]})
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "NOT_FOUND"

    # Add non-existent user to existing group -> 404
    g = client.post("/groups", json={"name": "Flatmates"}).json()
    res = client.post(f"/groups/{g['id']}/members", json={"user_id": "usr_nonexistent"})
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "NOT_FOUND"

    # List members of non-existent group -> 404
    res = client.get("/groups/grp_nonexistent/members")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "NOT_FOUND"
