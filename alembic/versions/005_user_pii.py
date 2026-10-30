"""Add user_pii table for encrypted VPA storage and blind indexing.

Revision ID: 005_user_pii
Revises: 004_tamper_evident_ledger
Create Date: 2026-10-31

"""

import sqlalchemy as sa

from alembic import op

revision: str = "005_user_pii"
down_revision: str | None = "004_tamper_evident_ledger"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None


def upgrade() -> None:
    op.create_table(
        "user_pii",
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("vpa_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("vpa_nonce", sa.LargeBinary(), nullable=False),
        sa.Column("vpa_key_id", sa.String(length=64), nullable=False),
        sa.Column("vpa_blind_index", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_user_pii_blind_index", "user_pii", ["vpa_blind_index"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_user_pii_blind_index", table_name="user_pii")
    op.drop_table("user_pii")
