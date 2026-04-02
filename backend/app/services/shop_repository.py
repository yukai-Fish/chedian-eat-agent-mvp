import csv
import os
import sqlite3
from pathlib import Path
from threading import Lock
from typing import Dict, List


BASE_DIR = Path(__file__).resolve().parents[2]
DB_PATH = Path(os.getenv("SQLITE_DB_PATH", str(BASE_DIR / "data" / "chedian.db")))
SCHEMA_PATH = BASE_DIR / "data" / "schema.sql"
SEED_CSV_PATH = BASE_DIR / "data" / "shops_mock.csv"

_init_lock = Lock()
_initialized = False


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(schema_sql)


def _table_has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(str(row["name"]) == column for row in rows)


def _ensure_compat_columns(conn: sqlite3.Connection) -> None:
    if not _table_has_column(conn, "usage_events", "anonymous_id"):
        conn.execute("ALTER TABLE usage_events ADD COLUMN anonymous_id TEXT")
    if not _table_has_column(conn, "usage_events", "user_id"):
        conn.execute("ALTER TABLE usage_events ADD COLUMN user_id TEXT")

    if not _table_has_column(conn, "feedback_submissions", "anonymous_id"):
        conn.execute("ALTER TABLE feedback_submissions ADD COLUMN anonymous_id TEXT")
    if not _table_has_column(conn, "feedback_submissions", "user_id"):
        conn.execute("ALTER TABLE feedback_submissions ADD COLUMN user_id TEXT")


def _seed_from_csv_if_empty(conn: sqlite3.Connection) -> None:
    row = conn.execute("SELECT COUNT(1) AS cnt FROM shops").fetchone()
    if row and int(row["cnt"]) > 0:
        return

    with open(SEED_CSV_PATH, "r", encoding="utf-8-sig") as f:
        records = list(csv.DictReader(f))

    conn.executemany(
        """
        INSERT INTO shops (
            id, name, campus, area, avg_price, open_hours, tastes, scenes, tags, is_open
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                item["id"],
                item["name"],
                item["campus"],
                item["area"],
                int(item["avg_price"]),
                item["open_hours"],
                item["tastes"],
                item["scenes"],
                item["tags"],
                int(item.get("is_open", 1)),
            )
            for item in records
        ],
    )


def ensure_database() -> None:
    global _initialized
    if _initialized:
        return

    with _init_lock:
        if _initialized:
            return
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _connect() as conn:
            _ensure_schema(conn)
            _ensure_compat_columns(conn)
            _seed_from_csv_if_empty(conn)
            conn.commit()
        _initialized = True


def fetch_active_shops() -> List[Dict]:
    ensure_database()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, name, campus, area, avg_price, open_hours, tastes, scenes, tags, is_open
            FROM shops
            WHERE is_open = 1
            """
        ).fetchall()
    return [dict(row) for row in rows]


def count_shops() -> int:
    ensure_database()
    with _connect() as conn:
        row = conn.execute("SELECT COUNT(1) AS cnt FROM shops WHERE is_open = 1").fetchone()
    return int(row["cnt"]) if row else 0
