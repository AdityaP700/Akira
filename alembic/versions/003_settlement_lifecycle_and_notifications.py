"""Add settlement reference, provider intent, provider events, and notifications.

Revision ID: 003_settlement_lifecycle_and_notifications
Revises: 002_user_token_hash
Create Date: 2026-10-30

"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "003_settlement_lifecycle_and_notifications"
down_revision: str | None = "002_user_token_hash"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None


def upgrade() -> None:
    # 1. Add columns to settlements
    with op.batch_alter_table("settlements") as batch_op:
        batch_op.add_column(sa.Column("reference", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("created_by", sa.BigInteger(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column(
                "provider_intent",
                sa.JSON().with_variant(JSONB(), "postgresql"),
                nullable=True,
            )
        )
        batch_op.create_foreign_key(
            "fk_settlements_created_by",
            "users",
            ["created_by"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_index("ix_settlements_reference", ["reference"], unique=True)

    # 2. Create provider_events table
    op.create_table(
        "provider_events",
        sa.Column("event_id", sa.String(length=64), primary_key=True, nullable=False),
        sa.Column("reference", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("amount_paise", sa.BigInteger(), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_provider_events_reference", "provider_events", ["reference"])

    # 3. Create notifications table
    op.create_table(
        "notifications",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            primary_key=True,
            nullable=False,
        ),
        sa.Column("public_id", sa.String(length=32), unique=True, nullable=False),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column(
            "group_id",
            sa.BigInteger(),
            sa.ForeignKey("groups.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("data", sa.JSON().with_variant(JSONB(), "postgresql"), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_notifications_user_read", "notifications", ["user_id", "read_at"])
    op.create_index("ix_notifications_user_created", "notifications", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_notifications_user_created", table_name="notifications")
    op.drop_index("ix_notifications_user_read", table_name="notifications")
    op.drop_table("notifications")

    op.drop_index("ix_provider_events_reference", table_name="provider_events")
    op.drop_table("provider_events")

    with op.batch_alter_table("settlements") as batch_op:
        batch_op.drop_index("ix_settlements_reference")
        batch_op.drop_constraint("fk_settlements_created_by", type_="foreignkey")
        batch_op.drop_column("provider_intent")
        batch_op.drop_column("updated_at")
        batch_op.drop_column("created_by")
        batch_op.drop_column("reference")
