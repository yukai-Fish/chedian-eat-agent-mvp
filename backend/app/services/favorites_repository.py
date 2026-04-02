from __future__ import annotations

import sqlite3
from typing import Dict, List, Optional

from app.services.shop_repository import DB_PATH, ensure_database


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def add_favorite(
    *,
    user_id: str,
    shop_id: str,
    shop_name: Optional[str] = None,
    anonymous_id: Optional[str] = None,
    source: str = "web",
) -> int:
    ensure_database()
    with _connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO user_favorites (user_id, anonymous_id, shop_id, shop_name, source)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, shop_id) DO UPDATE SET
              anonymous_id = excluded.anonymous_id,
              shop_name = excluded.shop_name,
              source = excluded.source
            """,
            (user_id, anonymous_id, shop_id, shop_name, source),
        )
        conn.commit()
        return int(cursor.lastrowid or 0)


def remove_favorite(*, user_id: str, shop_id: str) -> None:
    ensure_database()
    with _connect() as conn:
        conn.execute(
            "DELETE FROM user_favorites WHERE user_id = ? AND shop_id = ?",
            (user_id, shop_id),
        )
        conn.commit()


def list_favorites(*, user_id: str, limit: int = 100) -> List[Dict[str, object]]:
    ensure_database()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, user_id, anonymous_id, shop_id, shop_name, source, created_at
            FROM user_favorites
            WHERE user_id = ?
            ORDER BY datetime(created_at) DESC
            LIMIT ?
            """,
            (user_id, int(limit)),
        ).fetchall()
    return [dict(row) for row in rows]

