"""Add HMAC hash chain columns to ledger_entries and groups.

Revision ID: 004_tamper_evident_ledger
Revises: 003_settlement_lifecycle_and_notifications
Create Date: 2026-10-30

"""

import sqlalchemy as sa

from alembic import op

revision: str = "004_tamper_evident_ledger"
down_revision: str | None = "003_settlement_lifecycle_and_notifications"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None


def upgrade() -> None:
    with op.batch_alter_table("ledger_entries") as batch_op:
        batch_op.add_column(sa.Column("prev_hash", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("entry_hash", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("key_id", sa.String(length=64), nullable=True))

    with op.batch_alter_table("groups") as batch_op:
        batch_op.add_column(sa.Column("ledger_head_hash", sa.String(length=64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("groups") as batch_op:
        batch_op.drop_column("ledger_head_hash")

    with op.batch_alter_table("ledger_entries") as batch_op:
        batch_op.drop_column("key_id")
        batch_op.drop_column("entry_hash")
        batch_op.drop_column("prev_hash")
