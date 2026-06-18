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
