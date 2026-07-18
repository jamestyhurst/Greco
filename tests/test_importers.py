"""Importer tests — pure, no network.

Covers filename name recovery (feature 5) and the chess.com mis-route fix (#33:
a pasted PGN whose [Site] mentions chess.com must load as raw PGN, not raise).
"""
from pathlib import Path

import pytest

from importers import load_pgn, parse_players_from_filename


def test_parse_vs_patterns():
    assert parse_players_from_filename(Path("Magnus vs Hikaru.pgn")) == ("Magnus", "Hikaru")
    assert parse_players_from_filename(Path("A_vs_B.pgn")) == ("A", "B")
    assert parse_players_from_filename(Path("A_vs_B, Blitz, 2024.pgn")) == ("A", "B")


def test_parse_requires_vs_not_bare_hyphen():
    # A bare " - " is deliberately not a separator (avoids false names from
    # ordinary filenames like "My Game - Draft Copy.pgn").
    assert parse_players_from_filename(Path("A - B.pgn")) == (None, None)
    assert parse_players_from_filename(Path("My Game - Draft Copy.pgn")) == (None, None)


def test_parse_handles_none():
    assert parse_players_from_filename(None) == (None, None)
    assert parse_players_from_filename(
        Path("2026-05-19 JamesTortoise vs NinaTitova (Rapid, 1-0).pgn")
    ) == ("JamesTortoise", "NinaTitova")
    assert parse_players_from_filename(
        Path("redwood1978_vs_JamesTortoise_2025.10.05.pgn")
    ) == ("redwood1978", "JamesTortoise")


def test_parse_no_confident_match():
    assert parse_players_from_filename(Path("randomgame.pgn")) == (None, None)
    assert parse_players_from_filename(Path("12345.pgn")) == (None, None)


def test_pasted_pgn_mentioning_chesscom_loads_as_raw():
    pgn = (
        '[Event "Live Chess"]\n'
        '[Site "https://www.chess.com/game/live/123"]\n\n'
        "1. e4 e5 2. Nf3 Nc6 *"
    )
    text, src = load_pgn(pgn)
    assert "inline PGN" in src and "Nf3" in text


def test_bare_chesscom_url_needs_username():
    """A chess.com URL with no linked username fails with guidance, offline."""
    with pytest.raises(ValueError) as exc:
        load_pgn("https://www.chess.com/game/live/123")
    assert "username" in str(exc.value).lower()


# ---------------------------------------------------------------------------
# Chess.com — URL parsing and archive-walking (fake HTTP client, no network)
# ---------------------------------------------------------------------------

def test_chesscom_game_url_id_extraction():
    from importers import CHESSCOM_GAME_URL_RE
    for url in (
        "https://www.chess.com/game/live/144714224998",
        "https://chess.com/game/daily/987654",
        "https://www.chess.com/live/game/12345678",
        "www.chess.com/game/1122",
    ):
        assert CHESSCOM_GAME_URL_RE.search(url), url
    m = CHESSCOM_GAME_URL_RE.search(
        "https://www.chess.com/game/live/144714224998?move=31"
    )
    assert m.group(1) == "144714224998"


class _FakeResp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeChesscomClient:
    """Fake httpx client serving a canned archive index + monthly archives."""

    def __init__(self, responses):
        self._responses = responses  # url -> _FakeResp
        self.requested = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url, **kw):
        self.requested.append(url)
        return self._responses.get(url, _FakeResp(404))


ARCHIVES_URL = "https://api.chess.com/pub/player/alice/games/archives"
MONTH_MAY = "https://api.chess.com/pub/player/alice/games/2026/05"
MONTH_JUN = "https://api.chess.com/pub/player/alice/games/2026/06"


def _game(gid, pgn='[Event "Live Chess"]\n1. e4 e5 *', rules="chess", winner="white"):
    return {
        "url": f"https://www.chess.com/game/live/{gid}",
        "pgn": pgn,
        "rules": rules,
        "time_class": "rapid",
        "end_time": 1750000000,
        "white": {"username": "alice", "result": "win" if winner == "white" else "resigned"},
        "black": {"username": "bob", "result": "win" if winner == "black" else "resigned"},
    }


def _wire(monkeypatch, responses):
    import importers as _imp
    fake = _FakeChesscomClient(responses)
    monkeypatch.setattr(_imp, "_make_http_client", lambda: fake)
    return fake


def test_fetch_chesscom_recent_games_newest_first(monkeypatch):
    _wire(monkeypatch, {
        ARCHIVES_URL: _FakeResp(200, {"archives": [MONTH_MAY, MONTH_JUN]}),
        MONTH_JUN: _FakeResp(200, {"games": [_game(1), _game(2), _game(3, rules="chess960")]}),
        MONTH_MAY: _FakeResp(200, {"games": [_game(4)]}),
    })
    from importers import fetch_chesscom_recent_games
    games = fetch_chesscom_recent_games("alice", max_games=10)
    # Newest first across months; the chess960 variant game is skipped.
    assert [g["id"] for g in games] == ["2", "1", "4"]
    assert games[0]["white"] == "alice"
    assert games[0]["result"] == "white"
    assert games[0]["time_class"] == "rapid"


def test_fetch_chesscom_recent_games_time_class_filter(monkeypatch):
    """time_class narrows while walking, so max_games counts matching games."""
    _wire(monkeypatch, {
        ARCHIVES_URL: _FakeResp(200, {"archives": [MONTH_JUN]}),
        MONTH_JUN: _FakeResp(200, {"games": [
            dict(_game(1), time_class="blitz"),
            _game(2),                              # rapid (the default in _game)
            dict(_game(3), time_class="bullet"),
            _game(4),
        ]}),
    })
    from importers import fetch_chesscom_recent_games
    games = fetch_chesscom_recent_games("alice", max_games=10, time_class="rapid")
    assert [g["id"] for g in games] == ["4", "2"]
    assert all(g["time_class"] == "rapid" for g in games)


def test_load_from_chesscom_matches_game_and_stops_early(monkeypatch):
    fake = _wire(monkeypatch, {
        ARCHIVES_URL: _FakeResp(200, {"archives": [MONTH_MAY, MONTH_JUN]}),
        MONTH_JUN: _FakeResp(200, {"games": [_game(1), _game(2, pgn='[Event "Target"]\n1. d4 *')]}),
        MONTH_MAY: _FakeResp(200, {"games": [_game(4)]}),
    })
    from importers import load_from_chesscom
    pgn, src = load_from_chesscom("https://www.chess.com/game/live/2", username="alice")
    assert "Target" in pgn and "2" in src
    # Lazy walk: the match was in the newest month, so the older month was
    # never downloaded.
    assert MONTH_MAY not in fake.requested


def test_load_from_chesscom_unknown_player(monkeypatch):
    _wire(monkeypatch, {ARCHIVES_URL: _FakeResp(404)})
    from importers import load_from_chesscom
    with pytest.raises(ValueError) as exc:
        load_from_chesscom("12345", username="alice")
    assert "alice" in str(exc.value)


def test_load_from_chesscom_not_in_recent_archives(monkeypatch):
    _wire(monkeypatch, {
        ARCHIVES_URL: _FakeResp(200, {"archives": [MONTH_JUN]}),
        MONTH_JUN: _FakeResp(200, {"games": [_game(1)]}),
    })
    from importers import load_from_chesscom
    with pytest.raises(ValueError) as exc:
        load_from_chesscom("999", username="alice")
    assert "not found" in str(exc.value)
