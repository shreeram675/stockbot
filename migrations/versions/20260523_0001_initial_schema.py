"""initial schema

Revision ID: 20260523_0001
Revises:
Create Date: 2026-05-23
"""

import sqlalchemy as sa
from alembic import op

revision = "20260523_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("telegram_user_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_telegram_user_id", "users", ["telegram_user_id"])
    op.create_table(
        "risk_preferences",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("custom_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_risk_preferences_user_id", "risk_preferences", ["user_id"])
    op.create_table(
        "portfolio_snapshots",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("portfolio_value", sa.Float(), nullable=False),
        sa.Column("invested_amount", sa.Float(), nullable=False),
        sa.Column("pnl", sa.Float(), nullable=False),
        sa.Column("daily_pnl", sa.Float(), nullable=True),
        sa.Column("allocation", sa.JSON(), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
    )
    op.create_index("ix_portfolio_snapshots_user_id", "portfolio_snapshots", ["user_id"])
    op.create_table(
        "holdings",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("snapshot_id", sa.String(length=36), sa.ForeignKey("portfolio_snapshots.id"), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("average_price", sa.Float(), nullable=False),
        sa.Column("market_price", sa.Float(), nullable=True),
        sa.Column("market_value", sa.Float(), nullable=False),
        sa.Column("gain_loss", sa.Float(), nullable=False),
        sa.Column("sector", sa.String(length=128), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint("snapshot_id", "symbol", name="uq_holding_snapshot_symbol"),
    )
    op.create_index("ix_holdings_snapshot_id", "holdings", ["snapshot_id"])
    op.create_index("ix_holdings_symbol", "holdings", ["symbol"])
    op.create_table(
        "recommendations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("risk_used", sa.String(length=32), nullable=False),
        sa.Column("recommendation", sa.Text(), nullable=False),
        sa.Column("context", sa.JSON(), nullable=False),
    )
    op.create_index("ix_recommendations_user_id", "recommendations", ["user_id"])
    op.create_table(
        "system_logs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("level", sa.String(length=20), nullable=False),
        sa.Column("event", sa.String(length=255), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
    )
    op.create_table(
        "alert_logs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("alert_type", sa.String(length=64), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("delivery_status", sa.String(length=64), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
    )
    op.create_index("ix_alert_logs_user_id", "alert_logs", ["user_id"])


def downgrade() -> None:
    op.drop_table("alert_logs")
    op.drop_table("system_logs")
    op.drop_table("recommendations")
    op.drop_table("holdings")
    op.drop_table("portfolio_snapshots")
    op.drop_table("risk_preferences")
    op.drop_table("users")

