"""add dhan auth tokens

Revision ID: 20260524_0002
Revises: 20260523_0001
Create Date: 2026-05-24
"""

from alembic import op
import sqlalchemy as sa

revision = "20260524_0002"
down_revision = "20260523_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dhan_auth_tokens",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("client_id", sa.String(length=64), nullable=True),
        sa.Column("encrypted_access_token", sa.Text(), nullable=False),
        sa.Column("token_expiry", sa.DateTime(timezone=True), nullable=True),
        sa.Column("token_source", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_dhan_auth_tokens_user_id", "dhan_auth_tokens", ["user_id"])
    op.create_index("ix_dhan_auth_tokens_client_id", "dhan_auth_tokens", ["client_id"])


def downgrade() -> None:
    op.drop_table("dhan_auth_tokens")

