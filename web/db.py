"""Database layer for Greco Web — Phase 4.

Switched from raw sqlite3 to SQLAlchemy 2.0. The public API (function
signatures and return types) is unchanged from Phase 3, so no callers need
updating. The SQLite file is still the backend; Phase 7 swaps the URL to
PostgreSQL without touching this module.

Alembic reads _DB_URL and models.Base.metadata to generate migrations:
    venv\\Scripts\\python -m alembic upgrade head   # apply pending
    venv\\Scripts\\python -m alembic stamp head     # adopt existing schema
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from sqlalchemy import create_engine, func, or_, select
from sqlalchemy.orm import sessionmaker

# Re-export User so callers do `from web.db import User` as before.
from web.models import Base, ReportOwnership
from web.models import User  # noqa: F401  (re-exported public symbol)

# ---------------------------------------------------------------------------
# Engine and session factory (module-level; monkeypatched by tests)
# ---------------------------------------------------------------------------

_DB_PATH = Path(__file__).resolve().parent.parent / "greco_web.db"
_DB_URL = f"sqlite:///{_DB_PATH}"

engine = create_engine(_DB_URL, connect_args={"check_same_thread": False})

# expire_on_commit=False keeps ORM attributes accessible after session.commit()
# so we can return detached User objects without DetachedInstanceError.
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


# ---------------------------------------------------------------------------
# Schema management
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Create all tables if they don't exist (idempotent).

    For production schema evolution use Alembic migrations instead of this
    function — `alembic upgrade head` is the canonical way to bring a DB up to
    date. init_db() is kept for test fixtures and the lifespan startup hook
    (which still does the right thing on a fresh install).
    """
    Base.metadata.create_all(engine)


# ---------------------------------------------------------------------------
# User queries
# ---------------------------------------------------------------------------

def get_user_by_id(user_id: int) -> Optional[User]:
    with SessionLocal() as session:
        return session.get(User, user_id)


def get_user_by_username(username: str) -> Optional[User]:
    with SessionLocal() as session:
        stmt = select(User).where(func.lower(User.username) == username.lower())
        return session.scalars(stmt).first()


def get_user_by_email(email: str) -> Optional[User]:
    with SessionLocal() as session:
        stmt = select(User).where(User.email == email.lower())
        return session.scalars(stmt).first()


def get_password_hash_by_username(username: str) -> Optional[tuple]:
    """Return (id, password_hash) for login checks, or None.
    Accepts either username (case-insensitive) or email (lowercased)."""
    lookup = username.lower()
    with SessionLocal() as session:
        stmt = select(User).where(
            or_(func.lower(User.username) == lookup, User.email == lookup)
        )
        user = session.scalars(stmt).first()
    if user is None:
        return None
    return (user.id, user.password_hash)


def user_count() -> int:
    with SessionLocal() as session:
        return session.scalar(select(func.count()).select_from(User)) or 0


def create_user(username: str, email: str, password_hash: str, role: str = "user") -> User:
    with SessionLocal() as session:
        user = User(username=username, email=email,
                    password_hash=password_hash, role=role)
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


def get_all_users() -> List[User]:
    with SessionLocal() as session:
        return list(session.scalars(select(User).order_by(User.id)).all())


def get_user_password_hash(user_id: int) -> Optional[str]:
    with SessionLocal() as session:
        user = session.get(User, user_id)
    return user.password_hash if user else None


# ---------------------------------------------------------------------------
# Report ownership
# ---------------------------------------------------------------------------

def create_report_ownership(report_id: int, user_id: int) -> None:
    with SessionLocal() as session:
        # INSERT OR IGNORE equivalent: skip if already exists
        existing = session.get(ReportOwnership, report_id)
        if existing is None:
            session.add(ReportOwnership(report_id=report_id, user_id=user_id))
            session.commit()


def get_report_owner_id(report_id: int) -> Optional[int]:
    with SessionLocal() as session:
        row = session.get(ReportOwnership, report_id)
    return row.user_id if row else None


def get_user_report_ids(user_id: int) -> List[int]:
    with SessionLocal() as session:
        stmt = (
            select(ReportOwnership.report_id)
            .where(ReportOwnership.user_id == user_id)
            .order_by(ReportOwnership.report_id.desc())
        )
        return list(session.scalars(stmt).all())
