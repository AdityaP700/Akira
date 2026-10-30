"""Add token_hash to users.

Revision ID: 002_user_token_hash
Revises: 001_initial_schema
Create Date: 2026-10-30

"""

import sqlalchemy as sa

from alembic import op

revision: str = "002_user_token_hash"
down_revision: str | None = "001_initial_schema"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("token_hash", sa.String(length=64), nullable=True))
        batch_op.create_index("ix_users_token_hash", ["token_hash"], unique=True)


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_index("ix_users_token_hash")
        batch_op.drop_column("token_hash")
