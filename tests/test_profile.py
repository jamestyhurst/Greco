"""Tests for Greco Online Phase 6 — Profile routes.

GET  /profile          — renders profile page for logged-in user
POST /profile          — saves Lichess username, redirects back
GET  /profile/lichess-games — returns recent Lichess games as JSON

All tests use dependency_overrides to bypass require_login and an
isolated tmp_db fixture so no real DB is needed.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import web.db as db_module
from web.auth import hash_password, require_login
from web.db import User, create_user, get_user_by_id, init_db
from web.main import app
from web.models import Base


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    test_engine = create_engine(
        f"sqlite:///{tmp_path}/test.db",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(test_engine)
    test_session = sessionmaker(bind=test_engine, expire_on_commit=False)
    monkeypatch.setattr(db_module, "engine", test_engine)
    monkeypatch.setattr(db_module, "SessionLocal", test_session)
    return tmp_path / "test.db"


@pytest.fixture()
def user(tmp_db) -> User:
    return create_user("alice", "alice@example.com", hash_password("pass1234"), "user")


def make_client(u: User) -> TestClient:
    app.dependency_overrides[require_login] = lambda: u
    return TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# GET /profile
# ---------------------------------------------------------------------------

def test_profile_page_renders_for_logged_in_user(tmp_db, user):
    client = make_client(user)
    try:
        r = client.get("/profile")
        assert r.status_code == 200
        assert "alice" in r.text
        assert "Lichess" in r.text
    finally:
        app.dependency_overrides.pop(require_login, None)


def test_profile_page_requires_login():
    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/profile", follow_redirects=False)
    assert r.status_code in (303, 307)


# ---------------------------------------------------------------------------
# POST /profile
# ---------------------------------------------------------------------------

def test_post_profile_saves_lichess_username(tmp_db, user):
    client = make_client(user)
    try:
        r = client.post("/profile", data={"lichess_username": "DrNykterstein"},
                        follow_redirects=False)
        assert r.status_code == 303
        saved = get_user_by_id(user.id)
        assert saved.lichess_username == "DrNykterstein"
    finally:
        app.dependency_overrides.pop(require_login, None)


def test_post_profile_clears_lichess_username_when_empty(tmp_db, user):
    from web.db import update_user_lichess_username
    update_user_lichess_username(user.id, "SomeOldUser")
    client = make_client(user)
    try:
        client.post("/profile", data={"lichess_username": ""},
                    follow_redirects=False)
        saved = get_user_by_id(user.id)
        assert saved.lichess_username is None
    finally:
        app.dependency_overrides.pop(require_login, None)


def test_post_profile_rejects_invalid_username(tmp_db, user):
    client = make_client(user)
    try:
        r = client.post("/profile", data={"lichess_username": "has spaces!"})
        assert r.status_code == 422
    finally:
        app.dependency_overrides.pop(require_login, None)


# ---------------------------------------------------------------------------
# GET /profile/lichess-games
# ---------------------------------------------------------------------------

def test_lichess_games_returns_400_when_no_username_set(tmp_db, user):
    client = make_client(user)
    try:
        r = client.get("/profile/lichess-games")
        assert r.status_code == 400
    finally:
        app.dependency_overrides.pop(require_login, None)


def test_lichess_games_calls_lichess_api_and_returns_json(tmp_db, user, monkeypatch):
    from web.db import update_user_lichess_username
    update_user_lichess_username(user.id, "alice123")

    # The user stored in dependency_overrides doesn't have the updated value.
    # Refresh by reading from DB.
    from web.db import get_user_by_id
    fresh_user = get_user_by_id(user.id)

    import web.routers.profile as profile_mod
    monkeypatch.setattr(
        profile_mod, "_fetch_recent_games",
        lambda username, max_games=10: [
            {"id": "abcd1234", "white": "alice123", "black": "bob",
             "result": "white", "speed": "blitz",
             "lichess_url": "https://lichess.org/abcd1234"},
        ],
    )
    app.dependency_overrides[require_login] = lambda: fresh_user
    client = TestClient(app, raise_server_exceptions=True)
    try:
        r = client.get("/profile/lichess-games")
        assert r.status_code == 200
        data = r.json()
        assert data["lichess_username"] == "alice123"
        assert len(data["games"]) == 1
        assert data["games"][0]["id"] == "abcd1234"
    finally:
        app.dependency_overrides.pop(require_login, None)


# ---------------------------------------------------------------------------
# Chess.com profile field + GET /profile/chesscom-games
# ---------------------------------------------------------------------------

def test_post_profile_saves_chesscom_username(tmp_db, user):
    client = make_client(user)
    try:
        r = client.post("/profile", data={"chesscom_username": "JamesTortoise"},
                        follow_redirects=False)
        assert r.status_code == 303
        from web.db import get_user_by_id
        saved = get_user_by_id(user.id)
        assert saved.chesscom_username == "JamesTortoise"
    finally:
        app.dependency_overrides.pop(require_login, None)


def test_post_profile_rejects_invalid_chesscom_username(tmp_db, user):
    client = make_client(user)
    try:
        r = client.post("/profile", data={"chesscom_username": "has spaces!"})
        assert r.status_code == 422
    finally:
        app.dependency_overrides.pop(require_login, None)


def test_chesscom_games_returns_400_when_no_username_set(tmp_db, user):
    client = make_client(user)
    try:
        r = client.get("/profile/chesscom-games")
        assert r.status_code == 400
    finally:
        app.dependency_overrides.pop(require_login, None)


def test_chesscom_games_calls_api_and_returns_json(tmp_db, user, monkeypatch):
    from web.db import update_user_chesscom_username, get_user_by_id
    update_user_chesscom_username(user.id, "JamesTortoise")
    fresh_user = get_user_by_id(user.id)

    import web.routers.profile as profile_mod
    monkeypatch.setattr(
        profile_mod, "fetch_chesscom_recent_games",
        lambda username, max_games=10: [
            {"id": "123", "url": "https://www.chess.com/game/live/123",
             "white": "JamesTortoise", "black": "bob", "result": "white",
             "time_class": "rapid", "end_time": 1750000000,
             "pgn": '[Event "Live Chess"]\n1. e4 *'},
        ],
    )
    app.dependency_overrides[require_login] = lambda: fresh_user
    client = TestClient(app, raise_server_exceptions=True)
    try:
        r = client.get("/profile/chesscom-games")
        assert r.status_code == 200
        data = r.json()
        assert data["chesscom_username"] == "JamesTortoise"
        assert len(data["games"]) == 1
        assert data["games"][0]["id"] == "123"
        # The PGN stays server-side; the browser posts the game URL back.
        assert "pgn" not in data["games"][0]
    finally:
        app.dependency_overrides.pop(require_login, None)


def test_chesscom_games_returns_502_on_fetch_error(tmp_db, user, monkeypatch):
    from web.db import update_user_chesscom_username, get_user_by_id
    update_user_chesscom_username(user.id, "baduser")
    fresh_user = get_user_by_id(user.id)

    import web.routers.profile as profile_mod
    monkeypatch.setattr(
        profile_mod, "fetch_chesscom_recent_games",
        lambda username, max_games=10: (_ for _ in ()).throw(RuntimeError("timeout")),
    )
    app.dependency_overrides[require_login] = lambda: fresh_user
    client = TestClient(app, raise_server_exceptions=False)
    try:
        r = client.get("/profile/chesscom-games")
        assert r.status_code == 502
    finally:
        app.dependency_overrides.pop(require_login, None)


# ---------------------------------------------------------------------------
# _fetch_recent_games — endpoint shape + NDJSON parsing
# ---------------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, text: str):
        self.text = text

    def raise_for_status(self):
        pass


class _FakeClient:
    """Stands in for the httpx client; records every request it receives."""

    def __init__(self, text: str, calls: list):
        self._text = text
        self._calls = calls

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url, headers=None, params=None):
        self._calls.append({"url": url, "headers": headers, "params": params})
        return _FakeResponse(self._text)


_NDJSON = (
    '{"id":"abcd1234","variant":"standard","speed":"blitz","winner":"black",'
    '"players":{"white":{"user":{"name":"alice123"}},"black":{"user":{"name":"bob"}}}}\n'
    '{"id":"efgh5678","variant":"standard","speed":"rapid",'
    '"players":{"white":{"user":{"name":"carol"}},"black":{"user":{"name":"alice123"}}}}\n'
)


def test_fetch_recent_games_uses_documented_lichess_endpoint(monkeypatch):
    """Regression: the endpoint is /api/games/user/{u}. The /api/user/{u}/games
    shape originally shipped in Phase 6 does not exist on Lichess (HTTP 404),
    and the route-level tests mock _fetch_recent_games so they could never
    catch it. This test pins the real URL and the NDJSON parsing together."""
    import web.routers.profile as profile_mod
    calls: list = []
    monkeypatch.setattr(
        profile_mod, "_make_http_client", lambda: _FakeClient(_NDJSON, calls)
    )
    games = profile_mod._fetch_recent_games("alice123", max_games=2)

    assert calls[0]["url"] == "https://lichess.org/api/games/user/alice123"
    assert calls[0]["headers"]["Accept"] == "application/x-ndjson"
    assert calls[0]["params"]["max"] == "2"
    assert [g["id"] for g in games] == ["abcd1234", "efgh5678"]
    assert games[0]["result"] == "black"   # explicit winner field
    assert games[1]["result"] == "draw"    # no winner key -> draw
    assert games[0]["lichess_url"] == "https://lichess.org/abcd1234"


def test_lichess_games_returns_502_on_fetch_error(tmp_db, user, monkeypatch):
    from web.db import update_user_lichess_username, get_user_by_id
    update_user_lichess_username(user.id, "baduser")
    fresh_user = get_user_by_id(user.id)

    import web.routers.profile as profile_mod
    monkeypatch.setattr(
        profile_mod, "_fetch_recent_games",
        lambda username, max_games=10: (_ for _ in ()).throw(RuntimeError("timeout")),
    )
    app.dependency_overrides[require_login] = lambda: fresh_user
    client = TestClient(app, raise_server_exceptions=False)
    try:
        r = client.get("/profile/lichess-games")
        assert r.status_code == 502
    finally:
        app.dependency_overrides.pop(require_login, None)
