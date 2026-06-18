"""Tests for Greco Online Phase 3 — user accounts and authentication.

Covers:
- Password hashing and verification (web/auth.py)
- DB layer: user CRUD, first-user-admin logic, report ownership (web/db.py)
- Auth HTTP routes: register, login, logout (web/routers/auth.py)
- require_login FastAPI dependency (web/auth.py)

All DB tests use a per-test temp DB via the tmp_db fixture so they never
touch the real greco_web.db.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import web.db as db_module
from web.auth import hash_password, require_login, verify_password
from web.db import (
    User,
    create_report_ownership,
    create_user,
    get_password_hash_by_username,
    get_report_owner_id,
    get_user_by_id,
    get_user_by_username,
    get_user_report_ids,
    init_db,
    user_count,
)
from web.main import app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    """Redirect all DB calls to a fresh temp database for test isolation."""
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(db_module, "_DB_PATH", db_path)
    init_db()
    return db_path


@pytest.fixture()
def web_client(tmp_db):
    """TestClient backed by an isolated temp database.

    Using the context manager triggers the FastAPI lifespan (which calls
    init_db()); since _DB_PATH is already patched, this is a safe no-op."""
    with TestClient(app, raise_server_exceptions=True) as client:
        yield client


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

def test_hash_roundtrip():
    pw = "correct horse battery staple"
    assert verify_password(pw, hash_password(pw))


def test_wrong_password_rejected():
    h = hash_password("secret123")
    assert not verify_password("wrong-password", h)


def test_hash_does_not_store_plaintext():
    pw = "hunter2"
    assert pw not in hash_password(pw)


def test_different_calls_produce_different_hashes():
    pw = "samepassword"
    assert hash_password(pw) != hash_password(pw)  # bcrypt uses a random salt


# ---------------------------------------------------------------------------
# DB layer — user CRUD
# ---------------------------------------------------------------------------

def test_user_count_starts_at_zero(tmp_db):
    assert user_count() == 0


def test_create_user_and_retrieve_by_id(tmp_db):
    h = hash_password("pass1234")
    u = create_user("alice", "alice@example.com", h, "user")
    fetched = get_user_by_id(u.id)
    assert fetched is not None
    assert fetched.username == "alice"
    assert fetched.email == "alice@example.com"
    assert fetched.role == "user"


def test_create_user_increments_count(tmp_db):
    h = hash_password("pass1234")
    create_user("bob", "bob@example.com", h)
    assert user_count() == 1


def test_get_user_by_username(tmp_db):
    h = hash_password("pass1234")
    create_user("charlie", "charlie@example.com", h)
    u = get_user_by_username("charlie")
    assert u is not None and u.email == "charlie@example.com"


def test_get_user_by_id_unknown_returns_none(tmp_db):
    assert get_user_by_id(999) is None


def test_get_user_by_username_unknown_returns_none(tmp_db):
    assert get_user_by_username("nobody") is None


def test_is_admin_property(tmp_db):
    h = hash_password("pass1234")
    admin = create_user("adm", "adm@example.com", h, "admin")
    user = create_user("usr", "usr@example.com", h, "user")
    assert admin.is_admin
    assert not user.is_admin


def test_password_hash_lookup_by_username(tmp_db):
    pw = "mypassword99"
    h = hash_password(pw)
    u = create_user("diana", "diana@example.com", h)
    result = get_password_hash_by_username("diana")
    assert result is not None
    uid, stored_hash = result
    assert uid == u.id
    assert verify_password(pw, stored_hash)


def test_password_hash_lookup_by_email(tmp_db):
    """Login accepts either username or email."""
    h = hash_password("pass1234")
    u = create_user("eve", "eve@example.com", h)
    result = get_password_hash_by_username("eve@example.com")
    assert result is not None and result[0] == u.id


def test_password_hash_lookup_unknown_returns_none(tmp_db):
    assert get_password_hash_by_username("noone") is None


# ---------------------------------------------------------------------------
# DB layer — report ownership
# ---------------------------------------------------------------------------

def test_create_and_get_report_ownership(tmp_db):
    h = hash_password("pass1234")
    u = create_user("frank", "frank@example.com", h)
    create_report_ownership(42, u.id)
    assert get_report_owner_id(42) == u.id


def test_get_report_owner_id_unknown_returns_none(tmp_db):
    assert get_report_owner_id(999) is None


def test_get_user_report_ids(tmp_db):
    h = hash_password("pass1234")
    u = create_user("grace", "grace@example.com", h)
    create_report_ownership(10, u.id)
    create_report_ownership(20, u.id)
    assert set(get_user_report_ids(u.id)) == {10, 20}


def test_duplicate_ownership_insert_is_ignored(tmp_db):
    h = hash_password("pass1234")
    u = create_user("henry", "henry@example.com", h)
    create_report_ownership(7, u.id)
    create_report_ownership(7, u.id)  # should not raise
    assert get_report_owner_id(7) == u.id


# ---------------------------------------------------------------------------
# Auth routes — registration
# ---------------------------------------------------------------------------

def test_register_get_returns_form(web_client):
    r = web_client.get("/auth/register")
    assert r.status_code == 200
    assert "Register" in r.text or "register" in r.text.lower()


def test_register_creates_user_and_redirects(web_client):
    r = web_client.post("/auth/register", data={
        "username": "newuser",
        "email": "newuser@example.com",
        "password": "goodpassword1",
        "confirm": "goodpassword1",
    }, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/"


def test_register_first_user_gets_admin_role(tmp_db, web_client):
    web_client.post("/auth/register", data={
        "username": "firstuser",
        "email": "first@example.com",
        "password": "goodpassword1",
        "confirm": "goodpassword1",
    })
    u = get_user_by_username("firstuser")
    assert u is not None and u.is_admin


def test_register_second_user_gets_regular_role(tmp_db, web_client):
    for name, email in [("admin1", "admin1@example.com"), ("user2", "user2@example.com")]:
        web_client.post("/auth/register", data={
            "username": name, "email": email,
            "password": "goodpassword1", "confirm": "goodpassword1",
        })
    u = get_user_by_username("user2")
    assert u is not None and not u.is_admin


def test_register_short_password_rejected(web_client):
    r = web_client.post("/auth/register", data={
        "username": "shortpw",
        "email": "shortpw@example.com",
        "password": "short",
        "confirm": "short",
    })
    assert r.status_code == 200   # form re-shown, not a redirect


def test_register_mismatched_passwords_rejected(web_client):
    r = web_client.post("/auth/register", data={
        "username": "mismatch",
        "email": "mismatch@example.com",
        "password": "goodpassword1",
        "confirm": "different123",
    })
    assert r.status_code == 200
    assert "match" in r.text.lower()


def test_register_invalid_username_rejected(web_client):
    r = web_client.post("/auth/register", data={
        "username": "ab",   # too short — min 3 chars
        "email": "ab@example.com",
        "password": "goodpassword1",
        "confirm": "goodpassword1",
    })
    assert r.status_code == 200


def test_register_duplicate_username_rejected(tmp_db, web_client):
    h = hash_password("pass1234")
    create_user("taken", "taken@example.com", h)
    r = web_client.post("/auth/register", data={
        "username": "taken",
        "email": "other@example.com",
        "password": "goodpassword1",
        "confirm": "goodpassword1",
    })
    assert r.status_code == 200
    assert "taken" in r.text.lower() or "username" in r.text.lower()


def test_register_duplicate_email_rejected(tmp_db, web_client):
    h = hash_password("pass1234")
    create_user("existing", "shared@example.com", h)
    r = web_client.post("/auth/register", data={
        "username": "newname",
        "email": "shared@example.com",
        "password": "goodpassword1",
        "confirm": "goodpassword1",
    })
    assert r.status_code == 200
    assert "email" in r.text.lower() or "account" in r.text.lower()


# ---------------------------------------------------------------------------
# Auth routes — login
# ---------------------------------------------------------------------------

def test_login_get_returns_form(web_client):
    r = web_client.get("/auth/login")
    assert r.status_code == 200
    assert "Log in" in r.text or "login" in r.text.lower()


def test_login_valid_credentials_redirect(tmp_db, web_client):
    create_user("loginuser", "loginuser@example.com", hash_password("goodpass1"))
    r = web_client.post("/auth/login", data={
        "username": "loginuser",
        "password": "goodpass1",
    }, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/"


def test_login_by_email_works(tmp_db, web_client):
    create_user("emaillogin", "emaillogin@example.com", hash_password("goodpass1"))
    r = web_client.post("/auth/login", data={
        "username": "emaillogin@example.com",
        "password": "goodpass1",
    }, follow_redirects=False)
    assert r.status_code == 303


def test_login_wrong_password_returns_401(tmp_db, web_client):
    create_user("wrongpw", "wrongpw@example.com", hash_password("correctpass"))
    r = web_client.post("/auth/login", data={
        "username": "wrongpw",
        "password": "wrongpassword",
    })
    assert r.status_code == 401


def test_login_unknown_user_returns_401(web_client):
    r = web_client.post("/auth/login", data={
        "username": "nobody",
        "password": "password123",
    })
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Auth routes — logout
# ---------------------------------------------------------------------------

def test_logout_redirects_to_login(tmp_db, web_client):
    # Establish a session first.
    web_client.post("/auth/register", data={
        "username": "logouttest",
        "email": "logouttest@example.com",
        "password": "goodpassword1",
        "confirm": "goodpassword1",
    })
    r = web_client.post("/auth/logout", follow_redirects=False)
    assert r.status_code == 303
    assert "login" in r.headers["location"]


def test_unauthenticated_index_redirects_to_login(web_client):
    """GET / without a session should redirect to /auth/login (PRD requirement)."""
    r = web_client.get("/", follow_redirects=False)
    assert r.status_code in (303, 307)
    assert "login" in r.headers["location"]
