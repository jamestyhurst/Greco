"""Profile routes — Greco Online Phase 6.

GET  /profile         — view and edit the current user's profile settings.
POST /profile         — save updated profile settings (Lichess + Chess.com usernames).
GET  /profile/lichess-games  — JSON: recent Lichess games for the linked account.
GET  /profile/chesscom-games — JSON: recent Chess.com games for the linked account.

The linked usernames are stored on the User row; the profile page lists each
account's recent games with a one-click Analyze button.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from importers import fetch_chesscom_recent_games, load_from_lichess, _make_http_client
from web.auth import require_login
from web.db import User, update_user_chesscom_username, update_user_lichess_username
from web.templates import render_profile

router = APIRouter()

_log = logging.getLogger("greco.web")

_LICHESS_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_-]{2,30}$")
_CHESSCOM_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_-]{3,25}$")


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
    chesscom_username: str = Form(""),
) -> HTMLResponse:
    """Save profile settings and redirect back."""
    li_name = (lichess_username or "").strip()
    if li_name and not _LICHESS_USERNAME_RE.match(li_name):
        raise HTTPException(
            status_code=422,
            detail="Lichess username may only contain letters, digits, _ and -.",
        )
    cc_name = (chesscom_username or "").strip()
    if cc_name and not _CHESSCOM_USERNAME_RE.match(cc_name):
        raise HTTPException(
            status_code=422,
            detail="Chess.com username may only contain letters, digits, _ and -.",
        )
    update_user_lichess_username(current_user.id, li_name or None)
    update_user_chesscom_username(current_user.id, cc_name or None)
    return RedirectResponse("/profile?saved=1", status_code=303)


@router.get("/profile/chesscom-games")
def chesscom_recent_games(current_user: User = Depends(require_login)) -> JSONResponse:
    """Return the user's 10 most recent Chess.com games as JSON.

    Requires chesscom_username to be set on the user's profile. The PGN is
    deliberately NOT included — the Analyze button posts the game URL and the
    server re-fetches, keeping one code path for pasted URLs and one-click.
    """
    cu = getattr(current_user, "chesscom_username", None)
    if not cu:
        raise HTTPException(status_code=400, detail="No Chess.com username set in your profile.")

    try:
        games = fetch_chesscom_recent_games(cu, max_games=10)
    except Exception as exc:
        _log.warning("Chess.com games fetch failed for %s: %s", cu, exc)
        raise HTTPException(status_code=502, detail=f"Could not fetch games from Chess.com: {exc}")

    slim = [{k: g[k] for k in ("id", "url", "white", "black", "result", "time_class")}
            for g in games]
    return JSONResponse({"games": slim, "chesscom_username": cu})


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


# The documented games-export endpoint (https://lichess.org/api#tag/Games).
# NOTE the shape: /api/games/user/{u} — NOT /api/user/{u}/games, which 404s.
LICHESS_GAMES_API = "https://lichess.org/api/games/user/{username}"


def _fetch_recent_games(username: str, max_games: int = 10) -> list:
    """Fetch recent games from the Lichess NDJSON API."""
    url = LICHESS_GAMES_API.format(username=username)
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
