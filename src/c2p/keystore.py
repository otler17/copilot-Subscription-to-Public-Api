"""SQLite-backed API key store."""
from __future__ import annotations

import secrets
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from . import SETTINGS


SCHEMA = """
CREATE TABLE IF NOT EXISTS keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    secret TEXT NOT NULL UNIQUE,
    max_rpm INTEGER DEFAULT 0,        -- 0 = unlimited
    allow_models TEXT DEFAULT '',     -- comma-separated; '' = all
    revoked INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL,
    last_used_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_keys_secret ON keys(secret);
"""


@dataclass
class ApiKey:
    id: int
    name: str
    secret: str
    max_rpm: int
    allow_models: str
    revoked: bool
    created_at: int
    last_used_at: Optional[int]

    @property
    def models(self) -> list[str]:
        return [m.strip() for m in self.allow_models.split(",") if m.strip()]


def _conn() -> sqlite3.Connection:
    db_path: Path = SETTINGS.keys_db
    db_path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(db_path)
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    return c


def _row_to_key(row: sqlite3.Row) -> ApiKey:
    return ApiKey(
        id=row["id"],
        name=row["name"],
        secret=row["secret"],
        max_rpm=row["max_rpm"],
        allow_models=row["allow_models"] or "",
        revoked=bool(row["revoked"]),
        created_at=row["created_at"],
        last_used_at=row["last_used_at"],
    )


def add_key(name: str, max_rpm: int = 0, allow_models: Iterable[str] = ()) -> ApiKey:
    secret = "sk-" + name.lower().replace(" ", "-") + "-" + secrets.token_hex(24)
    models_csv = ",".join(allow_models)
    now = int(time.time())
    with _conn() as c:
        c.execute(
            "INSERT INTO keys(name, secret, max_rpm, allow_models, created_at) "
            "VALUES (?,?,?,?,?)",
            (name, secret, max_rpm, models_csv, now),
        )
        row = c.execute("SELECT * FROM keys WHERE name=?", (name,)).fetchone()
    return _row_to_key(row)


def list_keys(include_revoked: bool = True) -> list[ApiKey]:
    with _conn() as c:
        q = "SELECT * FROM keys"
        if not include_revoked:
            q += " WHERE revoked=0"
        q += " ORDER BY created_at DESC"
        return [_row_to_key(r) for r in c.execute(q)]


def revoke(name_or_secret: str) -> bool:
    with _conn() as c:
        cur = c.execute(
            "UPDATE keys SET revoked=1 WHERE name=? OR secret=?",
            (name_or_secret, name_or_secret),
        )
        return cur.rowcount > 0


def lookup(secret: str) -> Optional[ApiKey]:
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM keys WHERE secret=? AND revoked=0", (secret,)
        ).fetchone()
        if not row:
            return None
        c.execute("UPDATE keys SET last_used_at=? WHERE id=?",
                  (int(time.time()), row["id"]))
        return _row_to_key(row)


def get_by_name(name: str) -> Optional[ApiKey]:
    with _conn() as c:
        row = c.execute("SELECT * FROM keys WHERE name=?", (name,)).fetchone()
        return _row_to_key(row) if row else None
