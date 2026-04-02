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
