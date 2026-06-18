"""Authentication routes: register, login, logout — Greco Online Phase 3."""
from __future__ import annotations

import re
from typing import Optional

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from web.auth import (
    clear_session,
    hash_password,
    set_session_user,
    verify_password,
)
from web.db import (
    create_user,
    get_password_hash_by_username,
    get_user_by_email,
    get_user_by_username,
    user_count,
)
from web.templates import render_auth

router = APIRouter(prefix="/auth")

_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,30}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _validate_register(
    username: str, email: str, password: str, confirm: str
) -> Optional[str]:
    """Return an error message string if registration inputs are invalid, else None."""
    if not _USERNAME_RE.match(username):
        return "Username must be 3–30 characters: letters, digits, underscores only."
    if not _EMAIL_RE.match(email):
        return "Please enter a valid email address."
    if len(password) < 8:
        return "Password must be at least 8 characters."
    if password != confirm:
        return "Passwords do not match."
    if len(password.encode("utf-8")) > 72:
        return "Password is too long (max 72 bytes). Please choose a shorter one."
    if get_user_by_username(username):
        return "That username is already taken."
    if get_user_by_email(email):
        return "An account with that email already exists."
    return None


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

@router.get("/register", response_class=HTMLResponse)
async def register_form(request: Request) -> HTMLResponse:
    return HTMLResponse(render_auth("register"))


@router.post("/register", response_class=HTMLResponse)
async def register_submit(
    request: Request,
    username: str = Form(""),
    email: str = Form(""),
    password: str = Form(""),
    confirm: str = Form(""),
) -> HTMLResponse:
    username = username.strip()
    email = email.strip().lower()
    error = _validate_register(username, email, password, confirm)
    if error:
        return HTMLResponse(render_auth("register", error=error, prefill={"username": username, "email": email}))

    # First user ever → admin; all subsequent users → regular user.
    role = "admin" if user_count() == 0 else "user"
    pw_hash = hash_password(password)
    user = create_user(username, email, pw_hash, role)
    set_session_user(request, user.id)
    return RedirectResponse("/", status_code=303)


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request) -> HTMLResponse:
    return HTMLResponse(render_auth("login"))


@router.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    username: str = Form(""),
    password: str = Form(""),
) -> HTMLResponse:
    username = username.strip()
    result = get_password_hash_by_username(username)
    if result is None or not verify_password(password, result[1]):
        return HTMLResponse(
            render_auth("login", error="Invalid username / email or password.",
                        prefill={"username": username}),
            status_code=401,
        )
    user_id, _ = result
    set_session_user(request, user_id)
    return RedirectResponse("/", status_code=303)


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------

@router.post("/logout")
async def logout(request: Request) -> RedirectResponse:
    clear_session(request)
    return RedirectResponse("/auth/login", status_code=303)
