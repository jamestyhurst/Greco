"""add base column to report_ownership

Stores the human-readable game name (e.g. "Fischer vs Spassky") alongside
the report record so the My Reports listing page can show titles without
parsing HTML filenames. Nullable so existing Phase 3/4 rows are unaffected.

Revision ID: 002
Revises: 001
Create Date: 2026-06-18
"""
from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    # SQLite supports ADD COLUMN directly when the column is nullable.
    op.add_column("report_ownership", sa.Column("base", sa.Text(), nullable=True))


def downgrade() -> None:
    # Removing a column requires batch mode (table rebuild) in SQLite.
    with op.batch_alter_table("report_ownership") as batch_op:
        batch_op.drop_column("base")
