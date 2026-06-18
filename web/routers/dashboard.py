"""Dashboard routes — Greco Online Phase 5.

GET /my-reports  — logged-in user's report history (newest first).
GET /admin/users — admin-only: all users + report counts.

Both routes require login. The admin route additionally enforces the admin role;
non-admins receive a 403 HTML error rather than a redirect (they ARE logged in,
just not authorised to see all data).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse

from web.auth import require_login
from web.db import User, get_all_reports, get_all_users, get_user_reports
from web.templates import render_dashboard, render_admin_users

router = APIRouter()


@router.get("/my-reports", response_class=HTMLResponse)
def my_reports(current_user: User = Depends(require_login)) -> HTMLResponse:
    """Show the logged-in user's past analyses."""
    reports = get_user_reports(current_user.id)
    return HTMLResponse(render_dashboard(current_user, reports))


@router.get("/admin/users", response_class=HTMLResponse)
def admin_users(current_user: User = Depends(require_login)) -> HTMLResponse:
    """Admin view: all users and a summary of their report counts."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required.")
    users = get_all_users()
    all_reports = get_all_reports()
    # Count reports per user
    counts: dict[int, int] = {}
    for r in all_reports:
        counts[r.user_id] = counts.get(r.user_id, 0) + 1
    return HTMLResponse(render_admin_users(current_user, users, counts))
