"""Dashboard routes — Greco Online Phase 5.

GET  /my-reports          — logged-in user's report history (newest first).
GET  /my-reports/export   — CSV download of the user's report history.
POST /my-reports/{rid}/delete — soft-delete (remove ownership record).
GET  /admin/users         — admin-only: all users + report counts.
GET  /admin/reports/export — admin CSV: all reports across all users.

The admin routes enforce the admin role; non-admins receive 403.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse

from web.auth import require_login
from web.db import (
    User,
    delete_report_ownership,
    get_all_reports,
    get_all_users,
    get_report_owner_id,
    get_user_reports,
)
from web.templates import render_admin_users, render_dashboard

router = APIRouter()


# ---------------------------------------------------------------------------
# My Reports
# ---------------------------------------------------------------------------

@router.get("/my-reports", response_class=HTMLResponse)
def my_reports(current_user: User = Depends(require_login)) -> HTMLResponse:
    """Show the logged-in user's past analyses."""
    reports = get_user_reports(current_user.id)
    return HTMLResponse(render_dashboard(current_user, reports))


@router.get("/my-reports/export")
def my_reports_export(current_user: User = Depends(require_login)) -> StreamingResponse:
    """Download the user's report history as a CSV file."""
    reports = get_user_reports(current_user.id)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["report_id", "game", "date"])
    for r in reports:
        writer.writerow([
            r.report_id,
            r.base or "",
            r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else "",
        ])
    buf.seek(0)
    filename = f"greco-reports-{current_user.username}.csv"
    return StreamingResponse(
        buf,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/my-reports/{rid}/delete", response_class=HTMLResponse)
def delete_report(
    rid: int,
    current_user: User = Depends(require_login),
) -> HTMLResponse:
    """Remove a report from the user's history (ownership record only; file is kept)."""
    owner_id = get_report_owner_id(rid)
    if owner_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not your report.")
    if owner_id is None:
        raise HTTPException(status_code=404, detail="Report not found.")
    delete_report_ownership(rid)
    # Redirect back to My Reports after deletion.
    from fastapi.responses import RedirectResponse
    return RedirectResponse("/my-reports", status_code=303)


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------

@router.get("/admin/users", response_class=HTMLResponse)
def admin_users(current_user: User = Depends(require_login)) -> HTMLResponse:
    """Admin view: all users and a summary of their report counts."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required.")
    users = get_all_users()
    all_reports = get_all_reports()
    counts: dict[int, int] = {}
    for r in all_reports:
        counts[r.user_id] = counts.get(r.user_id, 0) + 1
    return HTMLResponse(render_admin_users(current_user, users, counts))


@router.get("/admin/reports/export")
def admin_reports_export(current_user: User = Depends(require_login)) -> StreamingResponse:
    """Admin CSV: all reports across all users (username, game, date)."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required.")
    all_users = {u.id: u.username for u in get_all_users()}
    all_reports = get_all_reports()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["report_id", "username", "game", "date"])
    for r in all_reports:
        writer.writerow([
            r.report_id,
            all_users.get(r.user_id, ""),
            r.base or "",
            r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else "",
        ])
    buf.seek(0)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    return StreamingResponse(
        buf,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="greco-all-reports-{stamp}.csv"'},
    )
