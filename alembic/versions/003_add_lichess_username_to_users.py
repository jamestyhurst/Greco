"""add lichess_username to users

Revision ID: 003
Revises: 002
Create Date: 2026-06-18

Adds an optional lichess_username column to the users table so users can
connect their Lichess account for one-click game import (Phase 6).
"""
from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("lichess_username", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("lichess_username")
