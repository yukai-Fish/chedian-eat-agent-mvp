from __future__ import annotations

import json
import sqlite3
from typing import Dict, List, Optional

from app.services.shop_repository import DB_PATH, ensure_database


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _load_json_list(raw: object) -> List[str]:
    text = str(raw or "").strip()
    if not text:
        return []
    try:
        data = json.loads(text)
    except Exception:
        return [item.strip() for item in text.split(",") if item and item.strip()]
    if not isinstance(data, list):
        return []
    return [str(item or "").strip() for item in data if str(item or "").strip()]


def get_profile_settings(*, user_id: str) -> Dict[str, object]:
    ensure_database()
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT user_id, anonymous_id, campus, taste_tags_json, dislikes_json, budget_preference, updated_at
            FROM user_preference_profiles
            WHERE user_id = ?
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()
    if not row:
        return {
            "user_id": user_id,
            "anonymous_id": None,
            "campus": "",
            "taste_tags": [],
            "dislikes": [],
            "budget_preference": "",
            "updated_at": None,
        }
    return {
        "user_id": str(row["user_id"] or "").strip(),
        "anonymous_id": str(row["anonymous_id"] or "").strip() or None,
        "campus": str(row["campus"] or "").strip(),
        "taste_tags": _load_json_list(row["taste_tags_json"]),
        "dislikes": _load_json_list(row["dislikes_json"]),
        "budget_preference": str(row["budget_preference"] or "").strip(),
        "updated_at": str(row["updated_at"] or "").strip() or None,
    }


def upsert_profile_settings(
    *,
    user_id: str,
    anonymous_id: Optional[str] = None,
    campus: Optional[str] = None,
    taste_tags: Optional[List[str]] = None,
    dislikes: Optional[List[str]] = None,
    budget_preference: Optional[str] = None,
    source: str = "miniprogram_profile",
) -> Dict[str, object]:
    ensure_database()
    existing = get_profile_settings(user_id=user_id)

    next_anonymous_id = (
        str(anonymous_id).strip()
        if anonymous_id is not None
        else str(existing.get("anonymous_id") or "").strip()
    ) or None
    next_campus = str(campus).strip() if campus is not None else str(existing.get("campus") or "").strip()
    next_taste_tags = list(taste_tags) if taste_tags is not None else list(existing.get("taste_tags") or [])
    next_dislikes = list(dislikes) if dislikes is not None else list(existing.get("dislikes") or [])
    next_budget_preference = (
        str(budget_preference).strip()
        if budget_preference is not None
        else str(existing.get("budget_preference") or "").strip()
    )

    taste_tags_json = json.dumps(next_taste_tags, ensure_ascii=False)
    dislikes_json = json.dumps(next_dislikes, ensure_ascii=False)
    source_value = str(source or "miniprogram_profile").strip() or "miniprogram_profile"

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO user_preference_profiles (
              user_id, anonymous_id, campus, taste_tags_json, dislikes_json, budget_preference, source
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
              anonymous_id = excluded.anonymous_id,
              campus = excluded.campus,
              taste_tags_json = excluded.taste_tags_json,
              dislikes_json = excluded.dislikes_json,
              budget_preference = excluded.budget_preference,
              source = excluded.source,
              updated_at = CURRENT_TIMESTAMP
            """,
            (
                user_id,
                next_anonymous_id,
                next_campus,
                taste_tags_json,
                dislikes_json,
                next_budget_preference,
                source_value,
            ),
        )
        conn.commit()

    return get_profile_settings(user_id=user_id)
