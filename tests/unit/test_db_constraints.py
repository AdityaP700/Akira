"""Tests verifying that database constraints reject invalid operations at the DB level."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

# Import models so Base.metadata is fully populated
import app.repositories.models  # noqa: F401

INSERT_GROUP_SQL = (
    "INSERT INTO groups (id, public_id, name, ledger_head_seq) VALUES (1, 'grp_1', 'Trip', 0)"
)


def test_db_rejects_zero_or_negative_amount_paise(db_session: Session) -> None:
    db_session.execute(text("INSERT INTO users (id, public_id, name) VALUES (1, 'usr_1', 'Alice')"))
    db_session.execute(text(INSERT_GROUP_SQL))

    # amount_paise = 0
    with pytest.raises(IntegrityError):
        db_session.execute(
            text(
                "INSERT INTO expenses (id, public_id, group_id, paid_by, amount_paise, "
                "description, split_type) VALUES (1, 'exp_1', 1, 1, 0, 'Test', 'EQUAL')"
            )
        )
        db_session.flush()

    db_session.rollback()


def test_db_rejects_negative_expense_share(db_session: Session) -> None:
    db_session.execute(text("INSERT INTO users (id, public_id, name) VALUES (1, 'usr_1', 'Alice')"))
    db_session.execute(text(INSERT_GROUP_SQL))
    db_session.execute(
        text(
            "INSERT INTO expenses (id, public_id, group_id, paid_by, amount_paise, "
            "description, split_type) VALUES (1, 'exp_1', 1, 1, 100, 'Test', 'EQUAL')"
        )
    )

    # owed_paise < 0
    with pytest.raises(IntegrityError):
        db_session.execute(
            text("INSERT INTO expense_shares (expense_id, user_id, owed_paise) VALUES (1, 1, -50)")
        )
        db_session.flush()

    db_session.rollback()


def test_db_rejects_duplicate_group_member(db_session: Session) -> None:
    db_session.execute(text("INSERT INTO users (id, public_id, name) VALUES (1, 'usr_1', 'Alice')"))
    db_session.execute(text(INSERT_GROUP_SQL))
    db_session.execute(text("INSERT INTO group_members (group_id, user_id) VALUES (1, 1)"))
    db_session.flush()

    # Duplicate primary key (group_id, user_id)
    with pytest.raises(IntegrityError):
        db_session.execute(text("INSERT INTO group_members (group_id, user_id) VALUES (1, 1)"))
        db_session.flush()

    db_session.rollback()


def test_db_rejects_settlement_self_transfer(db_session: Session) -> None:
    db_session.execute(text("INSERT INTO users (id, public_id, name) VALUES (1, 'usr_1', 'Alice')"))
    db_session.execute(text(INSERT_GROUP_SQL))

    # from_user == to_user
    with pytest.raises(IntegrityError):
        db_session.execute(
            text(
                "INSERT INTO settlements (id, public_id, group_id, from_user, to_user, "
                "amount_paise, status, method) "
                "VALUES (1, 'stl_1', 1, 1, 1, 100, 'CONFIRMED', 'OTHER')"
            )
        )
        db_session.flush()

    db_session.rollback()


def test_db_rejects_unknown_split_type(db_session: Session) -> None:
    db_session.execute(text("INSERT INTO users (id, public_id, name) VALUES (1, 'usr_1', 'Alice')"))
    db_session.execute(text(INSERT_GROUP_SQL))

    # split_type not in ('EQUAL', 'EXACT', 'SHARES')
    with pytest.raises(IntegrityError):
        db_session.execute(
            text(
                "INSERT INTO expenses (id, public_id, group_id, paid_by, amount_paise, "
                "description, split_type) VALUES (1, 'exp_1', 1, 1, 100, 'Test', 'PERCENTAGE')"
            )
        )
        db_session.flush()

    db_session.rollback()
