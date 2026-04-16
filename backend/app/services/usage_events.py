from __future__ import annotations

import os
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.services.shop_repository import ensure_database

BASE_DIR = Path(__file__).resolve().parents[2]
DB_PATH = Path(os.getenv("SQLITE_DB_PATH", str(BASE_DIR / "data" / "chedian.db")))


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def log_usage_event(
    *,
    event_type: str,
    uid: Optional[str] = None,
    anonymous_id: Optional[str] = None,
    user_id: Optional[str] = None,
    query_text: Optional[str] = None,
    shop_id: Optional[str] = None,
    shop_name: Optional[str] = None,
    source: str = "web",
    meta: Optional[Dict[str, Any]] = None,
) -> None:
    ensure_database()
    try:
        with _connect() as conn:
            conn.execute(
                """
                INSERT INTO usage_events (
                    event_type, uid, anonymous_id, user_id, query_text, shop_id, shop_name, source, meta_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_type,
                    uid,
                    anonymous_id,
                    user_id,
                    query_text,
                    shop_id,
                    shop_name,
                    source,
                    json.dumps(meta or {}, ensure_ascii=False),
                ),
            )
            conn.commit()
    except Exception as exc:  # noqa: BLE001
        logging.warning("Failed to log usage event: %s", exc)


def log_query_event(
    query: str,
    uid: Optional[str] = None,
    anonymous_id: Optional[str] = None,
    user_id: Optional[str] = None,
    source: str = "web",
    meta: Optional[Dict[str, Any]] = None,
) -> None:
    log_usage_event(
        event_type="query",
        uid=uid,
        anonymous_id=anonymous_id,
        user_id=user_id,
        query_text=query,
        source=source,
        meta=meta,
    )


def log_ranking_click_event(
    *,
    shop_id: str,
    shop_name: Optional[str] = None,
    uid: Optional[str] = None,
    anonymous_id: Optional[str] = None,
    user_id: Optional[str] = None,
    source: str = "web",
    meta: Optional[Dict[str, Any]] = None,
) -> None:
    log_usage_event(
        event_type="ranking_click",
        uid=uid,
        anonymous_id=anonymous_id,
        user_id=user_id,
        shop_id=shop_id,
        shop_name=shop_name,
        source=source,
        meta=meta,
    )


def fetch_recent_usage_events(days: int = 7) -> List[Dict[str, Any]]:
    ensure_database()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, event_type, uid, anonymous_id, user_id, query_text, shop_id, shop_name, source, meta_json, created_at
            FROM usage_events
            WHERE datetime(created_at) >= datetime('now', ?)
            ORDER BY datetime(created_at) DESC
            """,
            (f"-{days} day",),
        ).fetchall()
    return [dict(row) for row in rows]


def bind_anonymous_events_to_user(*, anonymous_id: str, user_id: str) -> int:
    ensure_database()
    anon = str(anonymous_id or "").strip()
    uid = str(user_id or "").strip()
    if not anon or not uid:
        return 0

    with _connect() as conn:
        cursor = conn.execute(
            """
            UPDATE usage_events
            SET user_id = ?
            WHERE anonymous_id = ?
              AND (user_id IS NULL OR user_id = '')
            """,
            (uid, anon),
        )
        conn.commit()
        return int(cursor.rowcount or 0)


def list_recent_query_history(*, user_id: str, limit: int = 20) -> List[str]:
    ensure_database()
    uid = str(user_id or "").strip()
    if not uid:
        return []

    max_limit = max(1, min(int(limit), 100))
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT query_text, MAX(datetime(created_at)) AS latest_at
            FROM usage_events
            WHERE event_type = 'query'
              AND user_id = ?
              AND query_text IS NOT NULL
              AND TRIM(query_text) <> ''
            GROUP BY query_text
            ORDER BY latest_at DESC
            LIMIT ?
            """,
            (uid, max_limit),
        ).fetchall()
    return [str(row["query_text"]) for row in rows if str(row["query_text"]).strip()]
