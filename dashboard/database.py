import json
import logging
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DB_DIR = Path(__file__).resolve().parent / "data"
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "dashboard.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS config (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS runs (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at    REAL NOT NULL,
                finished_at   REAL,
                status        TEXT NOT NULL DEFAULT 'running',
                offers_found  INTEGER DEFAULT 0,
                offers_sent   INTEGER DEFAULT 0,
                offers_new    INTEGER DEFAULT 0,
                error_message TEXT,
                created_at    TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS sent_offers (
                product_id  TEXT PRIMARY KEY,
                title       TEXT,
                price       REAL,
                discount    TEXT,
                sent_at     REAL NOT NULL,
                run_id      INTEGER REFERENCES runs(id)
            );

            CREATE TABLE IF NOT EXISTS run_logs (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id    INTEGER NOT NULL REFERENCES runs(id),
                level     TEXT NOT NULL DEFAULT 'INFO',
                message   TEXT NOT NULL,
                timestamp REAL NOT NULL
            );
        """)

        _ensure_default_config(conn)


DEFAULT_CONFIG = {
    "ML_CATEGORY": "",
    "ML_PAGES": "3",
    "MAX_OFFERS_PER_RUN": "10",
    "ML_PROMOTION_TYPE": "",
    "MIN_DISCOUNT": "0",
    "SEND_DELAY_SECONDS": "60",
    "CACHE_EXPIRY_DAYS": "7",
    "INCLUDE_KEYWORDS": "",
    "EXCLUDE_KEYWORDS": "",
}


def _ensure_default_config(conn):
    existing = {row["key"] for row in conn.execute("SELECT key FROM config").fetchall()}
    for key, val in DEFAULT_CONFIG.items():
        if key not in existing:
            conn.execute("INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)", (key, val))


def get_all_config() -> dict:
    with get_conn() as conn:
        rows = conn.execute("SELECT key, value FROM config").fetchall()
    return {row["key"]: row["value"] for row in rows}


def update_config(key: str, value: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO config (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


def update_config_batch(items: dict):
    with get_conn() as conn:
        for key, value in items.items():
            conn.execute(
                "INSERT INTO config (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )


def create_run(started_at: float) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO runs (started_at, status) VALUES (?, 'running')",
            (started_at,),
        )
        return cur.lastrowid


def finish_run(run_id: int, status: str, offers_found: int = 0, offers_sent: int = 0, offers_new: int = 0, error_message: Optional[str] = None):
    with get_conn() as conn:
        conn.execute(
            """UPDATE runs SET finished_at=?, status=?, offers_found=?,
               offers_sent=?, offers_new=?, error_message=?
               WHERE id=?""",
            (time.time(), status, offers_found, offers_sent, offers_new, error_message, run_id),
        )


def add_run_log(run_id: int, level: str, message: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO run_logs (run_id, level, message, timestamp) VALUES (?, ?, ?, ?)",
            (run_id, level, message, time.time()),
        )


def add_sent_offer(run_id: int, product_id: str, title: str, price: float, discount: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO sent_offers (product_id, title, price, discount, sent_at, run_id) VALUES (?, ?, ?, ?, ?, ?)",
            (product_id, title, price, discount, time.time(), run_id),
        )


def get_recent_runs(limit: int = 20) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_run_detail(run_id: int) -> Optional[dict]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if not row:
            return None
        result = dict(row)
        result["logs"] = [
            dict(r) for r in conn.execute(
                "SELECT * FROM run_logs WHERE run_id=? ORDER BY id", (run_id,)
            ).fetchall()
        ]
        result["offers"] = [
            dict(r) for r in conn.execute(
                "SELECT * FROM sent_offers WHERE run_id=? ORDER BY sent_at", (run_id,)
            ).fetchall()
        ]
    return result


def get_recent_offers(limit: int = 50) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM sent_offers ORDER BY sent_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]
