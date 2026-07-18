"""add chesscom_username to users

Revision ID: 004
Revises: 003
Create Date: 2026-07-18

Adds an optional chesscom_username column to the users table so users can
connect their Chess.com account for one-click game import, mirroring the
lichess_username column from migration 003.
"""
from alembic import op
import sqlalchemy as sa

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("chesscom_username", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("chesscom_username")
