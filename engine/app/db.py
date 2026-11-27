"""sqlite3 helpers: WAL + foreign_keys connections, init_db, typed insert/update/fetch, event outbox."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from .config import get_settings

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def connect(db_path: str | None = None) -> sqlite3.Connection:
    """Open a connection in autocommit mode with WAL, foreign keys and a busy timeout."""
    path = db_path or get_settings().db_path
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30.0, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Apply schema.sql (idempotent)."""
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))


def insert(conn: sqlite3.Connection, table: str, **row: Any) -> int:
    cols = list(row)
    sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})"
    cur = conn.execute(sql, [row[c] for c in cols])
    return int(cur.lastrowid or 0)


def upsert(conn: sqlite3.Connection, table: str, **row: Any) -> int:
    """INSERT OR REPLACE (idempotent on the primary key)."""
    cols = list(row)
    sql = f"INSERT OR REPLACE INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})"
    cur = conn.execute(sql, [row[c] for c in cols])
    return int(cur.lastrowid or 0)


def update(conn: sqlite3.Connection, table: str, where: dict[str, Any], values: dict[str, Any]) -> int:
    sets = ", ".join(f"{k} = ?" for k in values)
    conds = " AND ".join(f"{k} = ?" for k in where)
    cur = conn.execute(f"UPDATE {table} SET {sets} WHERE {conds}", [*values.values(), *where.values()])
    return cur.rowcount


def fetchone(conn: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> sqlite3.Row | None:
    return conn.execute(sql, params).fetchone()


def fetchall(conn: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
    return conn.execute(sql, params).fetchall()


def scalar(conn: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> Any:
    row = conn.execute(sql, params).fetchone()
    return None if row is None else row[0]


def insert_event(conn: sqlite3.Connection, topic: str, payload: dict[str, Any]) -> int:
    """Event outbox insert (SPEC §3 `events`)."""
    import json

    return insert(conn, "events", topic=topic, payload_json=json.dumps(payload, separators=(",", ":")), created_at=utcnow_iso())
