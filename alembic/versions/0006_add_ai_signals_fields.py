"""Add enhanced AI signals fields to market_signals table.

Revision ID: 0006
Revises: 0005
Create Date: 2026-03-22
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

_COLUMNS = (
    ("confidence", sa.Float()),
    ("bullish_strength", sa.Float()),
    ("bearish_strength", sa.Float()),
    ("volatility", sa.String(length=16)),
    ("triggering_event", sa.Text()),
    ("entry", sa.Float()),
    ("stop_loss", sa.Float()),
    ("target", sa.Float()),
    ("risk_reward", sa.Float()),
    ("atr", sa.Float()),
    ("max_position", sa.Float()),
    ("reasoning", sa.Text()),
)


def upgrade() -> None:
    # create_all in env.py may already have added these columns — skip if present
    bind = op.get_bind()
    existing = {col["name"] for col in inspect(bind).get_columns("market_signals")}
    for name, col_type in _COLUMNS:
        if name not in existing:
            op.add_column("market_signals", sa.Column(name, col_type, nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    existing = {col["name"] for col in inspect(bind).get_columns("market_signals")}
    for name, _ in reversed(_COLUMNS):
        if name in existing:
            op.drop_column("market_signals", name)
