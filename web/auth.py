"""Authentication helpers for Greco Web — Phase 3.

Covers:
- Password hashing / verification via the `bcrypt` library.
- Session read/write (the session cookie is signed by Starlette's SessionMiddleware).
- FastAPI dependencies: get_current_user (optional), require_login (enforced).

Design notes:
- We use `bcrypt` directly rather than passlib because passlib's compatibility
  shim breaks with bcrypt >= 4.x on Python 3.14 (password-truncation API change).
- Session data is minimal: only the integer user_id is stored in the signed cookie;
  the rest comes from the DB on each request so there are no stale-session issues.
- Passwords are validated to be 1–72 bytes after UTF-8 encoding; bcrypt's 72-byte
  limit is the algorithm's own constraint, not a passlib quirk.
"""
from __future__ import annotations

from typing import Optional

import bcrypt
from fastapi import Depends, Request

from web.db import User, get_user_by_id


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    """Return a bcrypt hash of *password* (suitable for storing in the DB)."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """Return True if *password* matches the stored *hashed* value."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------

def set_session_user(request: Request, user_id: int) -> None:
    request.session["user_id"] = user_id


def clear_session(request: Request) -> None:
    request.session.clear()


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------

async def get_current_user(request: Request) -> Optional[User]:
    """Return the logged-in User, or None if the session is unauthenticated.
    Inject into routes that need to *know* who is logged in but don't *require* it."""
    raw = request.session.get("user_id")
    if raw is None:
        return None
    try:
        return get_user_by_id(int(raw))
    except Exception:
        return None


class NotAuthenticated(Exception):
    """Raised when a protected route is accessed without a valid session."""


async def require_login(
    user: Optional[User] = Depends(get_current_user),
) -> User:
    """Dependency that enforces a logged-in session.
    The app-level exception handler converts NotAuthenticated → 303 redirect."""
    if user is None:
        raise NotAuthenticated()
    return user
