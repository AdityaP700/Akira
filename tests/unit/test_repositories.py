"""Unit tests for repository implementations."""

from sqlalchemy.orm import Session

from app.repositories import expenses, groups, idempotency, ledger, settlements, users


def test_user_repository(db_session: Session) -> None:
    u1 = users.create(db_session, "Alice")
    u2 = users.create(db_session, "Bob")

    assert u1.id is not None
    assert u1.public_id.startswith("usr_")
    assert u1.name == "Alice"

    fetched = users.get_by_id(db_session, u1.id)
    assert fetched is not None
    assert fetched.name == "Alice"

    fetched_pub = users.get_by_public_id(db_session, u2.public_id)
    assert fetched_pub is not None
    assert fetched_pub.name == "Bob"

    all_users = users.list_all(db_session)
    assert len(all_users) == 2


def test_group_repository(db_session: Session) -> None:
    u1 = users.create(db_session, "Alice")
    u2 = users.create(db_session, "Bob")

    g = groups.create(db_session, "Goa Trip")
    assert g.id is not None
    assert g.public_id.startswith("grp_")
    assert g.name == "Goa Trip"
    assert g.ledger_head_seq == 0

    groups.add_member(db_session, g.id, u1.id)
    groups.add_member(db_session, g.id, u2.id)

    members = groups.get_members(db_session, g.id)
    assert len(members) == 2
    assert groups.is_member(db_session, g.id, u1.id) is True
    assert groups.is_member(db_session, g.id, 999) is False

    locked_g = groups.lock_for_update(db_session, g.id)
    assert locked_g is not None
    assert locked_g.id == g.id


def test_expense_and_shares_repository(db_session: Session) -> None:
    u1 = users.create(db_session, "Alice")
    u2 = users.create(db_session, "Bob")
    g = groups.create(db_session, "Dinner")
    groups.add_member(db_session, g.id, u1.id)
    groups.add_member(db_session, g.id, u2.id)

    shares = {u1.id: 25000, u2.id: 25000}
    exp = expenses.create(
        db_session,
        group_id=g.id,
        paid_by=u1.id,
        amount_paise=50000,
        description="Seafood Dinner",
        split_type="EQUAL",
        shares=shares,
    )

    assert exp.id is not None
    assert exp.public_id.startswith("exp_")
    assert exp.amount_paise == 50000

    exp_list = expenses.list_by_group(db_session, g.id)
    assert len(exp_list) == 1
    assert exp_list[0].id == exp.id

    share_list = expenses.get_shares_by_group(db_session, g.id)
    assert len(share_list) == 2
    assert sum(s.owed_paise for s in share_list) == 50000


def test_settlement_repository(db_session: Session) -> None:
    u1 = users.create(db_session, "Alice")
    u2 = users.create(db_session, "Bob")
    g = groups.create(db_session, "Trip")

    stl = settlements.create(
        db_session,
        group_id=g.id,
        from_user=u2.id,
        to_user=u1.id,
        amount_paise=25000,
        status="CONFIRMED",
        method="UPI",
    )

    assert stl.id is not None
    assert stl.public_id.startswith("stl_")
    assert stl.amount_paise == 25000

    stl_list = settlements.list_by_group(db_session, g.id)
    assert len(stl_list) == 1
    assert stl_list[0].id == stl.id


def test_ledger_append_consecutive_seq(db_session: Session) -> None:
    g = groups.create(db_session, "Ledger Test")
    assert g.ledger_head_seq == 0

    e1 = ledger.append(
        db_session,
        group_id=g.id,
        entry_type="EXPENSE",
        ref_id=1,
        payload={"amount": 100},
    )
    assert e1.seq == 1
    assert g.ledger_head_seq == 1

    e2 = ledger.append(
        db_session,
        group_id=g.id,
        entry_type="SETTLEMENT",
        ref_id=2,
        payload={"amount": 50},
    )
    assert e2.seq == 2
    assert g.ledger_head_seq == 2

    entries = ledger.list_by_group(db_session, g.id)
    assert len(entries) == 2
    assert [e.seq for e in entries] == [1, 2]


def test_idempotency_repository(db_session: Session) -> None:
    rec = idempotency.save(
        db_session,
        scope="expenses",
        key="key-123",
        request_fingerprint="fp-abc",
        response_status=201,
        response_body={"id": "exp_123"},
    )
    assert rec.key == "key-123"

    fetched = idempotency.get(db_session, scope="expenses", key="key-123")
    assert fetched is not None
    assert fetched.response_status == 201

    # Update existing
    updated = idempotency.save(
        db_session,
        scope="expenses",
        key="key-123",
        request_fingerprint="fp-xyz",
        response_status=200,
        response_body={"id": "exp_123_updated"},
    )
    assert updated.response_status == 200
