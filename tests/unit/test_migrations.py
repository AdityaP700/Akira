"""Tests verifying Alembic migrations execute up and down without errors."""

from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, inspect

from alembic import command


def test_alembic_upgrade_and_downgrade(tmp_path: Path) -> None:
    db_file = tmp_path / "test_migration.db"
    db_url = f"sqlite:///{db_file}"

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    # Run upgrade to head
    command.upgrade(alembic_cfg, "head")

    # Verify tables exist
    engine = create_engine(db_url)
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    expected_tables = {
        "users",
        "groups",
        "group_members",
        "expenses",
        "expense_shares",
        "settlements",
        "ledger_entries",
        "idempotency_keys",
        "provider_events",
        "notifications",
        "alembic_version",
    }
    assert expected_tables.issubset(table_names)

    # Verify token_hash column added by 002_user_token_hash
    user_columns = {col["name"] for col in inspector.get_columns("users")}
    assert "token_hash" in user_columns

    # Verify settlement columns added by 003_settlement_lifecycle_and_notifications
    settlement_columns = {col["name"] for col in inspector.get_columns("settlements")}
    assert {"reference", "created_by", "updated_at", "provider_intent"}.issubset(settlement_columns)

    # Verify audit hash columns added by 004_tamper_evident_ledger
    ledger_columns = {col["name"] for col in inspector.get_columns("ledger_entries")}
    assert {"prev_hash", "entry_hash", "key_id"}.issubset(ledger_columns)

    group_columns = {col["name"] for col in inspector.get_columns("groups")}
    assert "ledger_head_hash" in group_columns

    # Run downgrade back to base
    command.downgrade(alembic_cfg, "base")

    inspector_after = inspect(engine)
    remaining_tables = set(inspector_after.get_table_names())
    assert "users" not in remaining_tables
    assert "expenses" not in remaining_tables
    assert "notifications" not in remaining_tables
    assert "provider_events" not in remaining_tables
