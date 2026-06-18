"""Profile routes — Greco Online Phase 6.

GET  /profile         — view and edit the current user's profile settings.
POST /profile         — save updated profile settings (Lichess username).
GET  /profile/lichess-games — JSON: fetch recent Lichess games for the
                              current user's linked Lichess account.

The Lichess username is stored on the User row and used in the My Reports
page to show recent games available for one-click analysis.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from importers import load_from_lichess, _make_http_client
from web.auth import require_login
from web.db import User, update_user_lichess_username
from web.templates import render_profile

router = APIRouter()

_log = logging.getLogger("greco.web")

_LICHESS_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_-]{2,30}$")


@router.get("/profile", response_class=HTMLResponse)
def profile_page(
    current_user: User = Depends(require_login),
    saved: str = "",
) -> HTMLResponse:
    """Show the user's profile / settings page."""
    return HTMLResponse(render_profile(current_user, saved=bool(saved)))


@router.post("/profile", response_class=HTMLResponse)
def profile_update(
    current_user: User = Depends(require_login),
    lichess_username: str = Form(""),
) -> HTMLResponse:
    """Save profile settings and redirect back."""
    username = (lichess_username or "").strip()
    if username and not _LICHESS_USERNAME_RE.match(username):
        raise HTTPException(
            status_code=422,
            detail="Lichess username may only contain letters, digits, _ and -.",
        )
    update_user_lichess_username(current_user.id, username or None)
    return RedirectResponse("/profile?saved=1", status_code=303)


@router.get("/profile/lichess-games")
def lichess_recent_games(current_user: User = Depends(require_login)) -> JSONResponse:
    """Return the user's 10 most recent Lichess games as JSON.

    Requires lichess_username to be set on the user's profile.
    Returns: {"games": [{"id": "...", "white": "...", "black": "...",
                          "result": "...", "variant": "...", "speed": "..."}]}
    """
    lu = current_user.lichess_username
    if not lu:
        raise HTTPException(status_code=400, detail="No Lichess username set in your profile.")

    try:
        games = _fetch_recent_games(lu, max_games=10)
    except Exception as exc:
        _log.warning("Lichess games fetch failed for %s: %s", lu, exc)
        raise HTTPException(status_code=502, detail=f"Could not fetch games from Lichess: {exc}")

    return JSONResponse({"games": games, "lichess_username": lu})


def _fetch_recent_games(username: str, max_games: int = 10) -> list:
    """Fetch recent games from the Lichess NDJSON API."""
    url = f"https://lichess.org/api/user/{username}/games"
    params = {
        "max": str(max_games),
        "perfType": "bullet,blitz,rapid,classical",
        "pgnInJson": "false",
        "opening": "false",
        "clocks": "false",
        "evals": "false",
    }
    with _make_http_client() as client:
        resp = client.get(
            url,
            headers={"Accept": "application/x-ndjson"},
            params=params,
        )
        resp.raise_for_status()

    games = []
    for line in resp.text.strip().splitlines():
        if not line.strip():
            continue
        try:
            import json
            g = json.loads(line)
            players = g.get("players", {})
            white = players.get("white", {}).get("user", {}).get("name", "?")
            black = players.get("black", {}).get("user", {}).get("name", "?")
            result = g.get("winner", "draw")
            games.append({
                "id": g.get("id", ""),
                "white": white,
                "black": black,
                "result": result,
                "variant": g.get("variant", "standard"),
                "speed": g.get("speed", ""),
                "lichess_url": f"https://lichess.org/{g.get('id', '')}",
            })
        except Exception:
            continue
    return games
