"""SQLite persistence for users, sessions, action tokens, and project ownership."""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from . import storage

DB_PATH = Path(os.environ.get("CERTIFY_AUTH_DB") or storage.DATA_DIR.parent / "accounts.sqlite3")


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 15000")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def init_db() -> None:
    with _connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                verified INTEGER NOT NULL DEFAULT 0,
                is_admin INTEGER NOT NULL DEFAULT 0,
                gmail_email TEXT,
                gmail_password TEXT,
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                csrf_hash TEXT NOT NULL,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS sessions_user_id ON sessions(user_id);
            CREATE TABLE IF NOT EXISTS action_tokens (
                token_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                purpose TEXT NOT NULL,
                expires_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS action_tokens_user_id ON action_tokens(user_id);
            CREATE TABLE IF NOT EXISTS project_owners (
                project_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS project_owners_user_id ON project_owners(user_id);
            """
        )


def create_user(user_id: str, email: str, password_hash: str, is_admin: bool, created_at: int) -> None:
    with _connect() as connection:
        connection.execute(
            "INSERT INTO users (id, email, password_hash, is_admin, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, email.strip().casefold(), password_hash, int(is_admin), created_at),
        )


def get_user_by_email(email: str) -> dict | None:
    with _connect() as connection:
        row = connection.execute(
            "SELECT * FROM users WHERE email = ?", (email.strip().casefold(),)
        ).fetchone()
    return dict(row) if row else None


def get_user_by_id(user_id: str) -> dict | None:
    with _connect() as connection:
        row = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def verify_action_token(token: str, purpose: str, now: int) -> dict | None:
    with _connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT users.* FROM action_tokens JOIN users ON users.id = action_tokens.user_id "
            "WHERE action_tokens.token_hash = ? AND action_tokens.purpose = ? AND action_tokens.expires_at > ?",
            (_digest(token), purpose, now),
        ).fetchone()
        if not row:
            return None
        connection.execute("DELETE FROM action_tokens WHERE token_hash = ?", (_digest(token),))
        if purpose == "verify":
            connection.execute("UPDATE users SET verified = 1 WHERE id = ?", (row["id"],))
    return dict(row)


def create_action_token(user_id: str, purpose: str, expires_at: int) -> str:
    token = secrets.token_urlsafe(32)
    with _connect() as connection:
        connection.execute("DELETE FROM action_tokens WHERE user_id = ? AND purpose = ?", (user_id, purpose))
        connection.execute(
            "INSERT INTO action_tokens (token_hash, user_id, purpose, expires_at) VALUES (?, ?, ?, ?)",
            (_digest(token), user_id, purpose, expires_at),
        )
    return token


def update_password(user_id: str, password_hash: str) -> None:
    with _connect() as connection:
        connection.execute("UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, user_id))
        connection.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        connection.execute("DELETE FROM action_tokens WHERE user_id = ?", (user_id,))


def create_session(user_id: str, expires_at: int) -> tuple[str, str]:
    session_token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    with _connect() as connection:
        connection.execute(
            "INSERT INTO sessions (token_hash, csrf_hash, user_id, expires_at) VALUES (?, ?, ?, ?)",
            (_digest(session_token), _digest(csrf_token), user_id, expires_at),
        )
    return session_token, csrf_token


def get_session_user(session_token: str, now: int) -> dict | None:
    with _connect() as connection:
        row = connection.execute(
            "SELECT users.id, users.email, users.is_admin, sessions.csrf_hash "
            "FROM sessions JOIN users ON users.id = sessions.user_id "
            "WHERE sessions.token_hash = ? AND sessions.expires_at > ? AND users.verified = 1",
            (_digest(session_token), now),
        ).fetchone()
        if not row:
            connection.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
            return None
    return dict(row)


def csrf_valid(session_user: dict, token: str) -> bool:
    return bool(token) and hmac.compare_digest(session_user["csrf_hash"], _digest(token))


def delete_session(session_token: str) -> None:
    with _connect() as connection:
        connection.execute("DELETE FROM sessions WHERE token_hash = ?", (_digest(session_token),))


def set_gmail_credentials(user_id: str, email: str, encrypted_password: str) -> None:
    with _connect() as connection:
        connection.execute(
            "UPDATE users SET gmail_email = ?, gmail_password = ? WHERE id = ?",
            (email.strip(), encrypted_password, user_id),
        )


def clear_gmail_credentials(user_id: str) -> None:
    with _connect() as connection:
        connection.execute(
            "UPDATE users SET gmail_email = NULL, gmail_password = NULL WHERE id = ?", (user_id,)
        )


def create_project(user_id: str, name: str, mode: str) -> dict:
    project = storage.create_project(name, mode)
    try:
        with _connect() as connection:
            connection.execute(
                "INSERT INTO project_owners (project_id, user_id) VALUES (?, ?)",
                (project["id"], user_id),
            )
    except Exception:
        storage._project_dir(project["id"]).rmdir()
        raise
    return project


def list_projects(user_id: str) -> list[dict]:
    with _connect() as connection:
        rows = connection.execute(
            "SELECT project_id FROM project_owners WHERE user_id = ? ORDER BY rowid", (user_id,)
        ).fetchall()
    projects = []
    for row in rows:
        try:
            projects.append(storage.load_project(row["project_id"]))
        except FileNotFoundError:
            continue
    return projects


def owns_project(user_id: str, project_id: str) -> bool:
    with _connect() as connection:
        row = connection.execute(
            "SELECT 1 FROM project_owners WHERE project_id = ? AND user_id = ?",
            (project_id, user_id),
        ).fetchone()
    return row is not None


def claim_legacy_projects(user_id: str) -> None:
    with _connect() as connection:
        connection.executemany(
            "INSERT OR IGNORE INTO project_owners (project_id, user_id) VALUES (?, ?)",
            [
                (directory.name, user_id)
                for directory in storage.DATA_DIR.iterdir()
                if directory.is_dir() and (directory / "project.json").is_file()
            ],
        )