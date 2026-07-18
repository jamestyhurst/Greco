"""
PGN source loaders.

Each loader returns (pgn_text, human_readable_source_description).
`load_pgn` auto-detects which loader to use from the user's input string.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional, Tuple

import httpx

from httpclient import make_http_client


LICHESS_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?lichess\.org/(?:embed/game/|game/|)([a-zA-Z0-9]{8})",
    re.IGNORECASE,
)
CHESSCOM_URL_RE = re.compile(r"(?:https?://)?(?:www\.)?chess\.com/", re.IGNORECASE)


def _make_http_client() -> httpx.Client:
    """OS-native-TLS client (see httpclient.py); short timeout for PGN fetches."""
    return make_http_client(timeout_seconds=30.0)


def load_from_file(path: Path) -> Tuple[str, str]:
    text = path.read_text(encoding="utf-8")
    return text, f"file: {path}"


def parse_players_from_filename(path) -> Tuple[Optional[str], Optional[str]]:
    """Best-effort recovery of player names from an informative filename.

    Recognises the common shapes the project itself uses, e.g.
    'Magnus vs Hikaru.pgn', 'A_vs_B.pgn', 'A - B.pgn',
    '2026-05-19 JamesTortoise vs NinaTitova (Rapid, 1-0).pgn',
    'redwood1978_vs_JamesTortoise_2025.10.05.pgn'. Returns (white, black), or
    (None, None) when no confident 'X vs Y' / 'X - Y' separator is found — so a
    non-matching filename silently falls back to the PGN headers / colours.

    Used only when the PGN lacks White/Black tags; purely additive convenience.
    """
    if not path:
        return (None, None)
    stem = Path(path).stem
    s = stem.replace("_", " ").strip()
    s = re.sub(r"\s*\([^)]*\)\s*$", "", s)              # trailing "(Rapid, 1-0)"
    s = re.sub(r"^\d{4}[-.]\d{2}[-.]\d{2}\s+", "", s)   # leading "2026-05-19 "
    # Require an explicit "vs"/"v"/"versus" separator. A bare " - " is intentionally
    # NOT accepted: it produces false names from ordinary filenames like
    # "My Game - Draft Copy.pgn", and real exports use "vs" anyway.
    m = re.search(r"^(.*?)\s+(?:vs\.?|v\.?|versus)\s+(.*)$", s, re.IGNORECASE)
    if not m:
        return (None, None)

    def _tidy(name: str) -> str:
        name = re.split(r"\s*,\s*", name)[0].strip()              # drop ", Blitz, 2024"
        name = re.sub(r"\s+\d{4}([-.]\d{2}([-.]\d{2})?)?$", "", name).strip()  # trailing date
        return name

    white, black = _tidy(m.group(1)), _tidy(m.group(2))

    def _ok(n: str) -> bool:
        return bool(n) and len(n) <= 40 and not n.isdigit()

    return (white, black) if _ok(white) and _ok(black) else (None, None)


def load_from_lichess(url_or_id: str) -> Tuple[str, str]:
    match = LICHESS_URL_RE.search(url_or_id)
    game_id = match.group(1) if match else url_or_id.strip()[:8]
    if not re.fullmatch(r"[a-zA-Z0-9]{8}", game_id):
        raise ValueError(f"Could not extract a Lichess game ID from: {url_or_id}")

    url = f"https://lichess.org/game/export/{game_id}"
    with _make_http_client() as client:
        response = client.get(
            url,
            headers={"Accept": "application/x-chess-pgn"},
            params={"clocks": "false", "evals": "false"},
        )
        response.raise_for_status()
    return response.text, f"Lichess game {game_id}"


# Chess.com game URLs carry a numeric id: /game/live/123, /game/daily/123,
# /live/game/123 (old style), or /game/123.
CHESSCOM_GAME_URL_RE = re.compile(
    r"chess\.com/(?:game/(?:live|daily)/|(?:live|daily)/game/|game/)(\d+)",
    re.IGNORECASE,
)

CHESSCOM_ARCHIVES_API = "https://api.chess.com/pub/player/{username}/games/archives"


def _iter_chesscom_games(client: httpx.Client, username: str, months_to_scan: int):
    """Yield a player's raw Chess.com game dicts, newest game first.

    Chess.com's public API has no per-game endpoint — games are published in
    monthly archive files per player. We fetch the archive index once, then
    walk the newest `months_to_scan` months backwards, yielding lazily so a
    caller that finds what it wants early never downloads older months.
    """
    # The API's canonical username form is lowercase; any other casing gets a
    # 301 redirect, which httpx does not follow by default.
    resp = client.get(CHESSCOM_ARCHIVES_API.format(username=username.lower()))
    if resp.status_code == 404:
        raise ValueError(f"No Chess.com player named {username!r}.")
    resp.raise_for_status()
    months = resp.json().get("archives", [])
    for month_url in reversed(months[-months_to_scan:]):
        r = client.get(month_url)
        if r.status_code != 200:
            continue
        # Within a month the list is oldest-first; newest-first for callers.
        for g in reversed(r.json().get("games", [])):
            yield g


def _chesscom_winner(game: dict) -> str:
    """Normalise Chess.com's per-player result codes to white/black/draw."""
    if game.get("white", {}).get("result") == "win":
        return "white"
    if game.get("black", {}).get("result") == "win":
        return "black"
    return "draw"


def fetch_chesscom_recent_games(
    username: str,
    max_games: int = 10,
    months_to_scan: int = 3,
    time_class: Optional[str] = None,
) -> list:
    """Return the player's most recent standard games as normalised dicts.

    Each dict: id, url, white, black, result (white/black/draw), time_class,
    end_time, pgn. Variants (Chess960 etc.) and PGN-less games are skipped.
    `time_class` optionally narrows to one Chess.com speed ("rapid", "blitz",
    "bullet", "daily") — filtering happens while walking, so max_games means
    "N games OF THIS SPEED", not "N games, some filtered away".
    """
    games = []
    with _make_http_client() as client:
        for g in _iter_chesscom_games(client, username, months_to_scan):
            if g.get("rules") != "chess" or not g.get("pgn"):
                continue
            if time_class and g.get("time_class") != time_class:
                continue
            m = CHESSCOM_GAME_URL_RE.search(g.get("url", ""))
            games.append({
                "id": m.group(1) if m else "",
                "url": g.get("url", ""),
                "white": g.get("white", {}).get("username", "?"),
                "black": g.get("black", {}).get("username", "?"),
                "result": _chesscom_winner(g),
                "time_class": g.get("time_class", ""),
                "end_time": g.get("end_time", 0),
                "pgn": g["pgn"],
            })
            if len(games) >= max_games:
                break
    return games


def load_from_chesscom(
    url_or_id: str, username: Optional[str] = None, months_to_scan: int = 6
) -> Tuple[str, str]:
    """Fetch a Chess.com game's PGN by its URL (or bare numeric id).

    Chess.com's public API is player-scoped (monthly archives), so resolving a
    game URL requires knowing ONE player in it: we walk `username`'s recent
    archives newest-first and match on the game id.
    """
    m = CHESSCOM_GAME_URL_RE.search(url_or_id)
    game_id = m.group(1) if m else url_or_id.strip()
    if not game_id.isdigit():
        raise ValueError(f"Could not extract a Chess.com game ID from: {url_or_id}")
    if not username:
        raise ValueError(
            "Fetching a Chess.com game needs a Chess.com username to look it up "
            "under (the public API is per-player). Save yours in your profile, "
            "or download the PGN from chess.com and upload it instead."
        )

    with _make_http_client() as client:
        for g in _iter_chesscom_games(client, username, months_to_scan):
            gm = CHESSCOM_GAME_URL_RE.search(g.get("url", ""))
            if gm and gm.group(1) == game_id and g.get("pgn"):
                return g["pgn"], f"Chess.com game {game_id}"
    raise ValueError(
        f"Game {game_id} was not found in {username}'s last "
        f"{months_to_scan} months of Chess.com archives."
    )


def load_pgn(source: str, chesscom_username: Optional[str] = None) -> Tuple[str, str]:
    """
    Auto-detect the source type:
    - existing file path  → load_from_file
    - lichess.org URL/ID  → load_from_lichess
    - chess.com URL       → load_from_chesscom (needs chesscom_username)
    - otherwise           → assume it's raw PGN text
    """
    if not source:
        raise ValueError("Empty source")

    # File path?
    candidate = Path(source)
    if candidate.exists() and candidate.is_file():
        return load_from_file(candidate)

    stripped = source.strip()
    # Does the input look like actual PGN (a tag pair or a numbered move)? If so it
    # is raw text, NOT a URL — even if a [Site]/[Event] tag mentions chess.com or
    # lichess. Only route to the URL loaders for a bare URL with no PGN content.
    looks_like_pgn = ("[" in source) or bool(re.search(r"\d+\.\s", source))

    if not looks_like_pgn:
        if LICHESS_URL_RE.search(stripped):
            return load_from_lichess(source)
        if CHESSCOM_URL_RE.search(stripped):
            return load_from_chesscom(source, username=chesscom_username)

    # Raw PGN text (must contain at least a header or a move).
    if looks_like_pgn:
        return source, "inline PGN text"

    raise ValueError(
        f"Could not figure out what {source!r} is. Pass a file path, a "
        "Lichess URL/ID, or raw PGN text."
    )
