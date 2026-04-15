from __future__ import annotations

import re
import sqlite3
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.services.shop_repository import DB_PATH, ensure_database


TASTE_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "辣": ("辣", "香辣", "麻辣", "重口"),
    "清淡": ("清淡", "不辣", "少辣", "淡口", "不油"),
    "甜": ("甜", "甜口"),
    "咸香": ("咸香", "下饭"),
}

SCENE_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "一个人": ("一个人", "单人", "独自", "自己吃"),
    "同学聚餐": ("聚餐", "室友", "同学", "朋友", "多人"),
    "夜宵": ("夜宵", "宵夜", "深夜"),
}

CAMPUS_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "清水河": ("清水河", "清水河校区"),
    "沙河": ("沙河", "沙河校区"),
}


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _inc(counter: Dict[str, float], key: str, weight: float = 1.0) -> None:
    if not key:
        return
    counter[key] = counter.get(key, 0.0) + weight


def _match_keywords(text: str, rules: Dict[str, Tuple[str, ...]], counter: Dict[str, float], weight: float = 1.0) -> None:
    normalized = (text or "").strip()
    if not normalized:
        return
    for label, keywords in rules.items():
        if any(token in normalized for token in keywords):
            _inc(counter, label, weight)


def _extract_budget_values(text: str) -> List[int]:
    normalized = (text or "").strip()
    if not normalized:
        return []
    values = [int(num) for num in re.findall(r"(\d{1,3})\s*(?:元|块|预算|以内|以下)?", normalized)]
    return [n for n in values if 5 <= n <= 300]


def _split_tags(text: Optional[str]) -> Iterable[str]:
    if not text:
        return []
    return [x.strip() for x in re.split(r"[|,;/，、\s]+", text) if x and x.strip()]


def _top_items(counter: Dict[str, float], limit: int = 2) -> List[str]:
    return [name for name, _ in sorted(counter.items(), key=lambda x: (-x[1], x[0]))[:limit]]


def _build_summary(tastes: List[str], scenes: List[str], campuses: List[str], budgets: List[int]) -> str:
    if not tastes and not scenes and not campuses and not budgets:
        return ""

    parts: List[str] = []
    if tastes:
        parts.append(f"口味偏好：{'、'.join(tastes)}")
    if scenes:
        parts.append(f"就餐场景偏好：{'、'.join(scenes)}")
    if campuses:
        parts.append(f"常用校区：{'、'.join(campuses)}")
    if budgets:
        parts.append(f"常见预算：{min(budgets)}-{max(budgets)}元")

    joined = "；".join(parts)
    return f"{joined}。请优先参考这些长期偏好，但与本次输入冲突时，以本次输入为准。"


def build_iterative_profile(
    *,
    uid: Optional[str] = None,
    anonymous_id: Optional[str] = None,
    user_id: Optional[str] = None,
    query_days: int = 30,
    feedback_days: int = 90,
) -> Dict[str, Any]:
    ensure_database()

    usage_filters = [
        ("uid", (uid or "").strip()),
        ("anonymous_id", (anonymous_id or "").strip()),
        ("user_id", (user_id or "").strip()),
    ]
    feedback_filters = [
        ("anonymous_id", (anonymous_id or "").strip()),
        ("user_id", (user_id or "").strip()),
    ]
    usage_filters = [(col, value) for col, value in usage_filters if value]
    feedback_filters = [(col, value) for col, value in feedback_filters if value]

    if not usage_filters and not feedback_filters:
        return {
            "hasProfile": False,
            "summary": "",
            "signals": {},
            "stats": {"queryCount": 0, "feedbackCount": 0},
        }

    taste_score: Dict[str, float] = defaultdict(float)
    scene_score: Dict[str, float] = defaultdict(float)
    campus_score: Dict[str, float] = defaultdict(float)
    budget_values: List[int] = []
    query_count = 0
    feedback_count = 0

    query_rows: List[sqlite3.Row] = []
    feedback_rows: List[sqlite3.Row] = []

    with _connect() as conn:
        if usage_filters:
            usage_where = " OR ".join([f"{col} = ?" for col, _ in usage_filters])
            usage_params = [value for _, value in usage_filters]
            query_rows = conn.execute(
                f"""
                SELECT query_text
                FROM usage_events
                WHERE event_type = 'query'
                  AND ({usage_where})
                  AND datetime(created_at) >= datetime('now', ?)
                ORDER BY datetime(created_at) DESC
                LIMIT 80
                """,
                (*usage_params, f"-{int(query_days)} day"),
            ).fetchall()

        if feedback_filters:
            feedback_where = " OR ".join([f"{col} = ?" for col, _ in feedback_filters])
            feedback_params = [value for _, value in feedback_filters]
            feedback_rows = conn.execute(
                f"""
                SELECT taste_tags, scene_tags, category, avg_price, rating, comment
                FROM feedback_submissions
                WHERE ({feedback_where})
                  AND datetime(created_at) >= datetime('now', ?)
                ORDER BY datetime(created_at) DESC
                LIMIT 80
                """,
                (*feedback_params, f"-{int(feedback_days)} day"),
            ).fetchall()

    for row in query_rows:
        text = str(row["query_text"] or "")
        if not text.strip():
            continue
        query_count += 1
        _match_keywords(text, TASTE_KEYWORDS, taste_score, 1.0)
        _match_keywords(text, SCENE_KEYWORDS, scene_score, 1.0)
        _match_keywords(text, CAMPUS_KEYWORDS, campus_score, 1.0)
        budget_values.extend(_extract_budget_values(text))

    for row in feedback_rows:
        feedback_count += 1
        rating = row["rating"]
        weight = 1.0
        if isinstance(rating, int):
            if rating >= 4:
                weight = 1.5
            elif rating <= 2:
                weight = 0.5

        for token in _split_tags(row["taste_tags"]):
            _match_keywords(token, TASTE_KEYWORDS, taste_score, weight)
        for token in _split_tags(row["scene_tags"]):
            _match_keywords(token, SCENE_KEYWORDS, scene_score, weight)
        _match_keywords(str(row["category"] or ""), TASTE_KEYWORDS, taste_score, weight * 0.5)
        _match_keywords(str(row["comment"] or ""), TASTE_KEYWORDS, taste_score, weight * 0.5)

        if isinstance(row["avg_price"], int) and 5 <= row["avg_price"] <= 300:
            budget_values.append(int(row["avg_price"]))

    top_tastes = _top_items(taste_score, 2)
    top_scenes = _top_items(scene_score, 2)
    top_campuses = _top_items(campus_score, 2)
    summary = _build_summary(top_tastes, top_scenes, top_campuses, budget_values)
    has_profile = bool(summary)

    signals: Dict[str, Any] = {
        "topTastes": top_tastes,
        "topScenes": top_scenes,
        "topCampuses": top_campuses,
        "budgetRange": {
            "min": min(budget_values) if budget_values else None,
            "max": max(budget_values) if budget_values else None,
        },
    }

    return {
        "hasProfile": has_profile,
        "summary": summary,
        "signals": signals if has_profile else {},
        "stats": {"queryCount": query_count, "feedbackCount": feedback_count},
    }
