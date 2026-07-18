"""Opt-in LIVE network smoke tests for the chess-site integrations.

These hit the real Lichess / Chess.com APIs, so they are skipped by default
(no flaky CI, no rate-limit burn). Run them whenever integration code changes:

    $env:GRECO_NETWORK_TESTS = "1"
    venv\\Scripts\\python -m pytest tests/test_live_network.py -v

Why they exist (Doctrine Law 1 — done = verified output): the Phase 6 Lichess
recent-games feature shipped calling a nonexistent endpoint and stayed green
for a month because every test mocked the fetch. Mocks verify our logic;
only a live call verifies the *contract* with the other side. These tests are
the cheap, repeatable version of "run it for real before calling it done."
"""
import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("GRECO_NETWORK_TESTS"),
    reason="live network smoke tests are opt-in: set GRECO_NETWORK_TESTS=1",
)

# A stable public account (Magnus Carlsen) and a docs-example game id — these
# existing is as close to a constant as the internet offers.
LICHESS_USER = "DrNykterstein"
LICHESS_GAME = "q7ZvsdUF"


def test_lichess_recent_games_live():
    from web.routers.profile import _fetch_recent_games

    games = _fetch_recent_games(LICHESS_USER, max_games=2)
    assert games, "expected at least one recent game"
    assert all(g["id"] and g["lichess_url"].startswith("https://lichess.org/")
               for g in games)


def test_lichess_game_export_live():
    from importers import load_from_lichess

    pgn, src = load_from_lichess(f"https://lichess.org/{LICHESS_GAME}")
    assert "[Event" in pgn and LICHESS_GAME in src


# James's own account — his games are the whole point of the integration.
CHESSCOM_USER = "JamesTortoise"


def test_chesscom_recent_games_live():
    from importers import fetch_chesscom_recent_games

    games = fetch_chesscom_recent_games(CHESSCOM_USER, max_games=3)
    assert games, "expected at least one recent game"
    assert all(g["pgn"].startswith("[") and g["url"] for g in games)


def test_chesscom_game_url_import_live():
    """End-to-end: take the newest real game's URL and resolve it back to PGN
    the same way the Analyze button will."""
    from importers import fetch_chesscom_recent_games, load_from_chesscom

    games = fetch_chesscom_recent_games(CHESSCOM_USER, max_games=1)
    assert games
    pgn, src = load_from_chesscom(games[0]["url"], username=CHESSCOM_USER)
    assert "[Event" in pgn
