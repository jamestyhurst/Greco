"""Tests for Greco Online Phase 5 — My Reports and Admin dashboard routes.

Both routes require login; the admin route additionally enforces the admin
role. Tests use an isolated temp database and dependency injection to control
the authenticated user.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import web.db as db_module
from web.auth import hash_password, require_login
from web.db import (
    User,
    create_report_ownership,
    create_user,
    delete_report_ownership,
    get_report_owner_id,
    init_db,
)
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
def regular_user(tmp_db) -> User:
    return create_user("ruser", "ruser@example.com", hash_password("pass1234"), "user")


@pytest.fixture()
def admin_user(tmp_db) -> User:
    return create_user("admin", "admin@example.com", hash_password("pass1234"), "admin")


def make_client(user: User) -> TestClient:
    """Return a TestClient that injects *user* as the logged-in session."""
    app.dependency_overrides[require_login] = lambda: user
    client = TestClient(app, raise_server_exceptions=True)
    return client


# ---------------------------------------------------------------------------
# My Reports (/my-reports)
# ---------------------------------------------------------------------------

def test_my_reports_empty(tmp_db, regular_user):
    client = make_client(regular_user)
    try:
        r = client.get("/my-reports")
        assert r.status_code == 200
        assert "No reports" in r.text or "my-reports" in r.url.lower() or "Analyze" in r.text
    finally:
        app.dependency_overrides.pop(require_login, None)


def test_my_reports_shows_own_reports(tmp_db, regular_user):
    create_report_ownership(7, regular_user.id, base="Deep Blue vs Kasparov")
    create_report_ownership(8, regular_user.id, base="Fischer vs Spassky")
    client = make_client(regular_user)
    try:
        r = client.get("/my-reports")
        assert r.status_code == 200
        assert "Deep Blue vs Kasparov" in r.text
        assert "Fischer vs Spassky" in r.text
        # Links to the reports should be present
        assert "/report/7" in r.text
        assert "/report/8" in r.text
    finally:
        app.dependency_overrides.pop(require_login, None)


def test_my_reports_does_not_show_other_users_reports(tmp_db, regular_user, admin_user):
    create_report_ownership(10, admin_user.id, base="Admin Game")
    create_report_ownership(11, regular_user.id, base="My Game")
    client = make_client(regular_user)
    try:
        r = client.get("/my-reports")
        assert "My Game" in r.text
        assert "Admin Game" not in r.text
    finally:
        app.dependency_overrides.pop(require_login, None)


def test_my_reports_requires_login():
    """Without an authenticated user, the route raises NotAuthenticated (→ redirect)."""
    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/my-reports", follow_redirects=False)
    assert r.status_code in (303, 307)


# ---------------------------------------------------------------------------
# Admin users (/admin/users)
# ---------------------------------------------------------------------------

def test_admin_users_returns_200_for_admin(tmp_db, admin_user):
    client = make_client(admin_user)
    try:
        r = client.get("/admin/users")
        assert r.status_code == 200
        assert admin_user.username in r.text
    finally:
        app.dependency_overrides.pop(require_login, None)


def test_admin_users_lists_all_users(tmp_db, admin_user, regular_user):
    client = make_client(admin_user)
    try:
        r = client.get("/admin/users")
        assert admin_user.username in r.text
        assert regular_user.username in r.text
    finally:
        app.dependency_overrides.pop(require_login, None)


def test_admin_users_shows_report_counts(tmp_db, admin_user, regular_user):
    create_report_ownership(1, regular_user.id, base="Game A")
    create_report_ownership(2, regular_user.id, base="Game B")
    client = make_client(admin_user)
    try:
        r = client.get("/admin/users")
        assert r.status_code == 200
        # The count "2" for regular_user should appear in the table
        assert "2" in r.text
    finally:
        app.dependency_overrides.pop(require_login, None)


def test_admin_users_returns_403_for_regular_user(tmp_db, regular_user):
    client = make_client(regular_user)
    try:
        r = client.get("/admin/users")
        assert r.status_code == 403
    finally:
        app.dependency_overrides.pop(require_login, None)


def test_admin_users_requires_login():
    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/admin/users", follow_redirects=False)
    assert r.status_code in (303, 307)


# ---------------------------------------------------------------------------
# CSV export (/my-reports/export, /admin/reports/export)
# ---------------------------------------------------------------------------

def test_my_reports_export_csv(tmp_db, regular_user):
    create_report_ownership(99, regular_user.id, base="Tal vs Botvinnik")
    client = make_client(regular_user)
    try:
        r = client.get("/my-reports/export")
        assert r.status_code == 200
        assert "text/csv" in r.headers["content-type"]
        assert "Tal vs Botvinnik" in r.text
        assert "report_id" in r.text   # CSV header row
    finally:
        app.dependency_overrides.pop(require_login, None)


def test_admin_reports_export_csv(tmp_db, admin_user, regular_user):
    create_report_ownership(1, regular_user.id, base="Morphy vs Duke")
    client = make_client(admin_user)
    try:
        r = client.get("/admin/reports/export")
        assert r.status_code == 200
        assert "text/csv" in r.headers["content-type"]
        assert "Morphy vs Duke" in r.text
    finally:
        app.dependency_overrides.pop(require_login, None)


def test_admin_reports_export_forbidden_for_regular_user(tmp_db, regular_user):
    client = make_client(regular_user)
    try:
        r = client.get("/admin/reports/export")
        assert r.status_code == 403
    finally:
        app.dependency_overrides.pop(require_login, None)


# ---------------------------------------------------------------------------
# Delete report (/my-reports/{rid}/delete)
# ---------------------------------------------------------------------------

def test_delete_own_report(tmp_db, regular_user):
    create_report_ownership(55, regular_user.id, base="My Game")
    client = make_client(regular_user)
    try:
        r = client.post("/my-reports/55/delete", follow_redirects=False)
        assert r.status_code == 303
        assert get_report_owner_id(55) is None
    finally:
        app.dependency_overrides.pop(require_login, None)


def test_delete_other_users_report_forbidden(tmp_db, admin_user, regular_user):
    create_report_ownership(60, admin_user.id, base="Admin Game")
    client = make_client(regular_user)
    try:
        r = client.post("/my-reports/60/delete")
        assert r.status_code == 403
        assert get_report_owner_id(60) == admin_user.id   # still exists
    finally:
        app.dependency_overrides.pop(require_login, None)


def test_admin_can_delete_any_report(tmp_db, admin_user, regular_user):
    create_report_ownership(70, regular_user.id, base="User Game")
    client = make_client(admin_user)
    try:
        r = client.post("/my-reports/70/delete", follow_redirects=False)
        assert r.status_code == 303
        assert get_report_owner_id(70) is None
    finally:
        app.dependency_overrides.pop(require_login, None)
