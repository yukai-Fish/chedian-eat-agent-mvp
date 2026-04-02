from __future__ import annotations

import sqlite3
from typing import Dict, List

from app.services.shop_repository import DB_PATH, ensure_database


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def save_feedback(record: Dict[str, object]) -> int:
    ensure_database()
    with _connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO feedback_submissions (
                feedback_type,
                store_name,
                anonymous_id,
                user_id,
                area,
                category,
                avg_price,
                rating,
                scene_tags,
                taste_tags,
                feature_tags,
                recommend_dish,
                short_intro,
                recommend_reason,
                comment,
                warning_note,
                source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.get("feedback_type"),
                record.get("store_name"),
                record.get("anonymous_id"),
                record.get("user_id"),
                record.get("area"),
                record.get("category"),
                record.get("avg_price"),
                record.get("rating"),
                record.get("scene_tags"),
                record.get("taste_tags"),
                record.get("feature_tags"),
                record.get("recommend_dish"),
                record.get("short_intro"),
                record.get("recommend_reason"),
                record.get("comment"),
                record.get("warning_note"),
                record.get("source", "frontend_user_feedback"),
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)


def suggest_store_names(keyword: str, limit: int = 8) -> List[str]:
    ensure_database()
    q = (keyword or "").strip()
    if not q:
        return []

    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT name
            FROM shops
            WHERE is_open = 1
              AND name LIKE ?
            ORDER BY name ASC
            LIMIT ?
            """,
            (f"%{q}%", int(limit)),
        ).fetchall()

    return [str(row["name"]) for row in rows if row and row["name"]]
