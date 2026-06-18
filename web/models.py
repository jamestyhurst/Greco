"""SQLAlchemy ORM models for Greco Web — Phase 4.

These models define the schema. Alembic reads them to generate migrations.
Application code imports from web.db (which re-exports User and provides
all CRUD functions); direct imports from here are for migrations only.

Phase 7 note: the SQLite → PostgreSQL swap requires only a URL change.
The one SQLite-specific choice here is COLLATE NOCASE on username. When
migrating to PostgreSQL, replace with a citext column or a partial lowercase
unique index, and update get_user_by_username to compare case-insensitively.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # COLLATE NOCASE makes username lookups case-insensitive in SQLite.
    # See module docstring for the PostgreSQL migration path.
    username: Mapped[str] = mapped_column(
        String(30, collation="NOCASE"), unique=True, nullable=False
    )
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="user")
    lichess_username: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


class ReportOwnership(Base):
    __tablename__ = "report_ownership"

    report_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    # Human-readable game title added in migration 002 (nullable for old rows).
    base: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
