"""Initial database schema.

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-10-30

"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "001_initial_schema"
down_revision: str | None = None
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None


def upgrade() -> None:
    # 1. users
    op.create_table(
        "users",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("public_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
        sa.CheckConstraint("length(trim(name)) BETWEEN 1 AND 100", name="chk_users_name_length"),
    )

    # 2. groups
    op.create_table(
        "groups",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("public_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("ledger_head_seq", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
        sa.CheckConstraint("length(trim(name)) BETWEEN 1 AND 100", name="chk_groups_name_length"),
    )

    # 3. group_members
    op.create_table(
        "group_members",
        sa.Column("group_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "joined_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("group_id", "user_id"),
    )

    # 4. expenses
    op.create_table(
        "expenses",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("public_id", sa.String(length=32), nullable=False),
        sa.Column("group_id", sa.BigInteger(), nullable=False),
        sa.Column("paid_by", sa.BigInteger(), nullable=False),
        sa.Column("amount_paise", sa.BigInteger(), nullable=False),
        sa.Column("description", sa.String(length=200), nullable=False),
        sa.Column("split_type", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["paid_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
        sa.CheckConstraint(
            "amount_paise > 0 AND amount_paise <= 100000000", name="chk_expenses_amount_paise"
        ),
        sa.CheckConstraint(
            "length(trim(description)) BETWEEN 1 AND 200", name="chk_expenses_description_length"
        ),
        sa.CheckConstraint(
            "split_type IN ('EQUAL', 'EXACT', 'SHARES')", name="chk_expenses_split_type"
        ),
    )
    op.create_index(
        "ix_expenses_group_created_id",
        "expenses",
        ["group_id", sa.text("created_at DESC"), sa.text("id DESC")],
    )

    # 5. expense_shares
    op.create_table(
        "expense_shares",
        sa.Column("expense_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("owed_paise", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["expense_id"], ["expenses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("expense_id", "user_id"),
        sa.CheckConstraint("owed_paise >= 0", name="chk_shares_owed_paise"),
    )
    op.create_index("ix_shares_user_id", "expense_shares", ["user_id"])

    # 6. settlements
    op.create_table(
        "settlements",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("public_id", sa.String(length=32), nullable=False),
        sa.Column("group_id", sa.BigInteger(), nullable=False),
        sa.Column("from_user", sa.BigInteger(), nullable=False),
        sa.Column("to_user", sa.BigInteger(), nullable=False),
        sa.Column("amount_paise", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="CONFIRMED", nullable=False),
        sa.Column("method", sa.String(length=20), server_default="OTHER", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["from_user"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["to_user"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
        sa.CheckConstraint(
            "amount_paise > 0 AND amount_paise <= 100000000",
            name="chk_settlements_amount_paise",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'SUCCESS', 'FAILED', 'CLAIMED', 'CONFIRMED', 'REJECTED')",
            name="chk_settlements_status",
        ),
        sa.CheckConstraint("method IN ('UPI', 'CASH', 'OTHER')", name="chk_settlements_method"),
        sa.CheckConstraint("from_user <> to_user", name="chk_settlements_no_self_transfer"),
    )
    op.create_index(
        "ix_settlements_group_created",
        "settlements",
        ["group_id", sa.text("created_at DESC")],
    )

    # 7. ledger_entries
    op.create_table(
        "ledger_entries",
        sa.Column("group_id", sa.BigInteger(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("entry_type", sa.String(length=20), nullable=False),
        sa.Column("ref_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "payload",
            sa.JSON().with_variant(JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("group_id", "seq"),
        sa.CheckConstraint(
            "entry_type IN ('EXPENSE', 'SETTLEMENT', 'REVERSAL')",
            name="chk_ledger_entry_type",
        ),
    )

    # 8. idempotency_keys
    op.create_table(
        "idempotency_keys",
        sa.Column("scope", sa.String(length=100), nullable=False),
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column(
            "response_body",
            sa.JSON().with_variant(JSONB(), "postgresql"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("scope", "key"),
    )


def downgrade() -> None:
    op.drop_table("idempotency_keys")
    op.drop_table("ledger_entries")
    op.drop_index("ix_settlements_group_created", table_name="settlements")
    op.drop_table("settlements")
    op.drop_index("ix_shares_user_id", table_name="expense_shares")
    op.drop_table("expense_shares")
    op.drop_index("ix_expenses_group_created_id", table_name="expenses")
    op.drop_table("expenses")
    op.drop_table("group_members")
    op.drop_table("groups")
    op.drop_table("users")
