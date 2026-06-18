"""SQLite persistence layer for Greco Web.

Phase 3 introduces user accounts; Phase 4 will migrate to SQLAlchemy + PostgreSQL.
For now we use the stdlib sqlite3 module with raw SQL — easy to swap later because
all DB access goes through this module's functions, nowhere else.

The DB file (greco_web.db) lives in the repo root and is gitignored (*.db rule).
init_db() is idempotent — safe to call on every startup.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

# DB lives beside config.json in the repo root.
_DB_PATH = Path(__file__).resolve().parent.parent / "greco_web.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")   # concurrent reads while writing
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """Create tables if they don't exist (idempotent)."""
    with _connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT UNIQUE NOT NULL COLLATE NOCASE,
                email         TEXT UNIQUE NOT NULL COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                role          TEXT NOT NULL DEFAULT 'user',
                created_at    TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS report_ownership (
                report_id  INTEGER PRIMARY KEY,
                user_id    INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
        """)


# ---------------------------------------------------------------------------
# Domain object
# ---------------------------------------------------------------------------

@dataclass
class User:
    id: int
    username: str
    email: str
    role: str           # 'user' or 'admin'

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


# ---------------------------------------------------------------------------
# User queries
# ---------------------------------------------------------------------------

def _row_to_user(row: sqlite3.Row) -> User:
    return User(id=row["id"], username=row["username"],
                email=row["email"], role=row["role"])


def get_user_by_id(user_id: int) -> Optional[User]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, username, email, role FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    return _row_to_user(row) if row else None


def get_user_by_username(username: str) -> Optional[User]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, username, email, role FROM users WHERE username = ?", (username,)
        ).fetchone()
    return _row_to_user(row) if row else None


def get_user_by_email(email: str) -> Optional[User]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, username, email, role FROM users WHERE email = ?", (email,)
        ).fetchone()
    return _row_to_user(row) if row else None


def get_user_password_hash(user_id: int) -> Optional[str]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT password_hash FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    return row["password_hash"] if row else None


def get_password_hash_by_username(username: str) -> Optional[tuple]:
    """Return (id, password_hash) for login checks, or None."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, password_hash FROM users WHERE username = ? OR email = ?",
            (username, username),
        ).fetchone()
    return (row["id"], row["password_hash"]) if row else None


def user_count() -> int:
    with _connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]


def create_user(username: str, email: str, password_hash: str, role: str = "user") -> User:
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO users (username, email, password_hash, role) VALUES (?, ?, ?, ?)",
            (username, email, password_hash, role),
        )
        return User(id=cur.lastrowid, username=username, email=email, role=role)


def get_all_users() -> List[User]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, username, email, role FROM users ORDER BY id"
        ).fetchall()
    return [_row_to_user(r) for r in rows]


# ---------------------------------------------------------------------------
# Report ownership
# ---------------------------------------------------------------------------

def create_report_ownership(report_id: int, user_id: int) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO report_ownership (report_id, user_id) VALUES (?, ?)",
            (report_id, user_id),
        )


def get_report_owner_id(report_id: int) -> Optional[int]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT user_id FROM report_ownership WHERE report_id = ?", (report_id,)
        ).fetchone()
    return row["user_id"] if row else None


def get_user_report_ids(user_id: int) -> List[int]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT report_id FROM report_ownership WHERE user_id = ? ORDER BY report_id DESC",
            (user_id,),
        ).fetchall()
    return [r["report_id"] for r in rows]
