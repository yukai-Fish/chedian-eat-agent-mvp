from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.services.shop_repository import ensure_database

BASE_DIR = Path(__file__).resolve().parents[2]
DB_PATH = Path(os.getenv("SQLITE_DB_PATH", str(BASE_DIR / "data" / "chedian.db")))

_CONTACT_KEY = "contact_wechat"
_DEFAULT_CONTACT_WECHAT = "chedian_bd_01"
_DEFAULT_IMAGE_BASE = "/assets/ads"
_LEGACY_ICON_IMAGE_URLS = {
    "/assets/tabbar/ginkgo-gold.png",
    "/assets/tabbar/xiaohui.png",
    "/assets/tabbar-v2/inquiry.png",
    "/assets/tabbar-v2/inquiry-active.png",
    "/assets/tabbar-v2/ads.png",
    "/assets/tabbar-v2/ads-active.png",
    "/assets/tabbar-v2/profile.png",
    "/assets/tabbar-v2/profile-active.png",
}
_DEFAULT_AD_SLOTS = [
    {
        "id": "ad-campus",
        "title": "校内食堂精选位",
        "subtitle": "面向正在搜索校园餐的学生",
        "scene": "校内高频曝光",
        "audience": "适合：食堂窗口、校内品牌档口",
        "price_label": "¥199 / 周",
        "image_url": f"{_DEFAULT_IMAGE_BASE}/campus-canteen.jpg",
        "landing_type": "none",
        "landing_value": "",
        "rank": 10,
        "is_active": 1,
    },
    {
        "id": "ad-west-gate",
        "title": "西门商圈高转化位",
        "subtitle": "晚餐与夜宵时段重点曝光",
        "scene": "夜间高转化流量",
        "audience": "适合：火锅、烧烤、小龙虾、夜宵门店",
        "price_label": "¥299 / 周",
        "image_url": f"{_DEFAULT_IMAGE_BASE}/westgate-night.jpg",
        "landing_type": "none",
        "landing_value": "",
        "rank": 20,
        "is_active": 1,
    },
    {
        "id": "ad-light-food",
        "title": "轻食咖啡白领位",
        "subtitle": "覆盖低脂、下午茶、学习场景",
        "scene": "轻食健身偏好场景",
        "audience": "适合：轻食、咖啡、茶饮品牌",
        "price_label": "¥239 / 周",
        "image_url": f"{_DEFAULT_IMAGE_BASE}/lightfood-cafe.jpg",
        "landing_type": "none",
        "landing_value": "",
        "rank": 30,
        "is_active": 1,
    },
]
_REALISTIC_SLOT_IMAGE_MAP = {
    "ad-campus": f"{_DEFAULT_IMAGE_BASE}/campus-canteen.jpg",
    "ad-west-gate": f"{_DEFAULT_IMAGE_BASE}/westgate-night.jpg",
    "ad-light-food": f"{_DEFAULT_IMAGE_BASE}/lightfood-cafe.jpg",
}


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _normalize_text(value: Any, *, max_length: int = 2000) -> str:
    text = str(value or "").strip()
    if max_length > 0 and len(text) > max_length:
        text = text[:max_length]
    return text


def _normalize_slot_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    slot_id = _normalize_text(payload.get("id"), max_length=80)
    if not slot_id:
        slot_id = f"ad-{uuid.uuid4().hex[:12]}"

    title = _normalize_text(payload.get("title"), max_length=80) or "未命名广告位"
    subtitle = _normalize_text(payload.get("subtitle"), max_length=180)
    scene = _normalize_text(payload.get("scene"), max_length=80)
    audience = _normalize_text(payload.get("audience"), max_length=180)
    price_label = _normalize_text(payload.get("priceLabel") or payload.get("price_label"), max_length=40)
    image_url = _normalize_text(payload.get("imageUrl") or payload.get("image_url"), max_length=1000)
    landing_type = _normalize_text(payload.get("landingType") or payload.get("landing_type"), max_length=30) or "none"
    if landing_type not in {"none", "store_detail", "miniprogram_path", "external_web", "copy_wechat"}:
        landing_type = "none"
    landing_value = _normalize_text(payload.get("landingValue") or payload.get("landing_value"), max_length=500)

    try:
        rank = int(payload.get("rank", 0) or 0)
    except (TypeError, ValueError):
        rank = 0

    is_active_raw = payload.get("isActive") if "isActive" in payload else payload.get("is_active", 1)
    is_active = 1 if bool(is_active_raw) else 0

    starts_at = _normalize_text(payload.get("startsAt") or payload.get("starts_at"), max_length=40)
    ends_at = _normalize_text(payload.get("endsAt") or payload.get("ends_at"), max_length=40)

    return {
        "id": slot_id,
        "title": title,
        "subtitle": subtitle,
        "scene": scene,
        "audience": audience,
        "price_label": price_label,
        "image_url": image_url,
        "landing_type": landing_type,
        "landing_value": landing_value,
        "rank": rank,
        "is_active": is_active,
        "starts_at": starts_at or None,
        "ends_at": ends_at or None,
    }


def _slot_row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id": str(row["id"]),
        "title": str(row["title"] or ""),
        "subtitle": str(row["subtitle"] or ""),
        "scene": str(row["scene"] or ""),
        "audience": str(row["audience"] or ""),
        "priceLabel": str(row["price_label"] or ""),
        "imageUrl": str(row["image_url"] or ""),
        "landingType": str(row["landing_type"] or "none"),
        "landingValue": str(row["landing_value"] or ""),
        "rank": int(row["rank"] or 0),
        "isActive": bool(int(row["is_active"] or 0)),
        "startsAt": str(row["starts_at"] or ""),
        "endsAt": str(row["ends_at"] or ""),
        "updatedAt": str(row["updated_at"] or ""),
    }


def _ensure_ads_seed(conn: sqlite3.Connection) -> None:
    row = conn.execute("SELECT COUNT(1) AS cnt FROM ad_slots").fetchone()
    if row and int(row["cnt"] or 0) > 0:
        return

    now = _now_iso()
    conn.executemany(
        """
        INSERT INTO ad_slots (
            id, title, subtitle, scene, audience, price_label, image_url,
            landing_type, landing_value, rank, is_active, starts_at, ends_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                item["id"],
                item["title"],
                item.get("subtitle") or None,
                item.get("scene") or None,
                item.get("audience") or None,
                item.get("price_label") or None,
                item.get("image_url") or None,
                item.get("landing_type") or "none",
                item.get("landing_value") or None,
                int(item.get("rank", 0)),
                int(item.get("is_active", 1)),
                item.get("starts_at"),
                item.get("ends_at"),
                now,
                now,
            )
            for item in _DEFAULT_AD_SLOTS
        ],
    )
    conn.execute(
        """
        INSERT INTO ad_settings(key, value, updated_at)
        VALUES(?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
        """,
        (_CONTACT_KEY, _DEFAULT_CONTACT_WECHAT, now),
    )


def _upgrade_legacy_slot_images(conn: sqlite3.Connection) -> int:
    """
    Backward-compatible migration:
    - If ad slots still point to old tabbar icon assets, replace them with realistic ad photos.
    - Do not overwrite custom images configured by operations.
    """
    updated = 0
    now = _now_iso()
    for slot_id, target_image in _REALISTIC_SLOT_IMAGE_MAP.items():
        row = conn.execute(
            "SELECT image_url FROM ad_slots WHERE id = ? LIMIT 1",
            (slot_id,),
        ).fetchone()
        if not row:
            continue
        current = _normalize_text(row["image_url"], max_length=1000)
        if current and current not in _LEGACY_ICON_IMAGE_URLS:
            continue
        conn.execute(
            """
            UPDATE ad_slots
            SET image_url = ?, updated_at = ?
            WHERE id = ?
            """,
            (target_image, now, slot_id),
        )
        updated += 1
    return updated


def _ensure_ready() -> None:
    ensure_database()
    with _connect() as conn:
        _ensure_ads_seed(conn)
        _upgrade_legacy_slot_images(conn)
        conn.commit()


def get_ads_contact_wechat() -> str:
    _ensure_ready()
    with _connect() as conn:
        row = conn.execute("SELECT value FROM ad_settings WHERE key = ?", (_CONTACT_KEY,)).fetchone()
    value = str(row["value"] if row and row["value"] is not None else "").strip()
    return value or _DEFAULT_CONTACT_WECHAT


def set_ads_contact_wechat(value: str) -> str:
    _ensure_ready()
    text = _normalize_text(value, max_length=80) or _DEFAULT_CONTACT_WECHAT
    now = _now_iso()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO ad_settings(key, value, updated_at)
            VALUES(?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            """,
            (_CONTACT_KEY, text, now),
        )
        conn.commit()
    return text


def list_public_ad_slots(*, limit: int = 10) -> List[Dict[str, Any]]:
    _ensure_ready()
    top_n = max(1, min(int(limit), 50))
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, title, subtitle, scene, audience, price_label, image_url,
                   landing_type, landing_value, rank, is_active, starts_at, ends_at, updated_at
            FROM ad_slots
            WHERE is_active = 1
              AND (starts_at IS NULL OR TRIM(starts_at) = '' OR datetime(starts_at) <= datetime('now'))
              AND (ends_at IS NULL OR TRIM(ends_at) = '' OR datetime(ends_at) >= datetime('now'))
            ORDER BY rank ASC, datetime(updated_at) DESC
            LIMIT ?
            """,
            (top_n,),
        ).fetchall()
    return [_slot_row_to_dict(row) for row in rows]


def list_admin_ad_slots(*, days: int = 30) -> List[Dict[str, Any]]:
    _ensure_ready()
    lookback = max(1, min(int(days), 365))
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT
              s.id, s.title, s.subtitle, s.scene, s.audience, s.price_label, s.image_url,
              s.landing_type, s.landing_value, s.rank, s.is_active, s.starts_at, s.ends_at, s.updated_at,
              COALESCE(total.total_clicks, 0) AS total_clicks,
              COALESCE(recent.recent_clicks, 0) AS recent_clicks
            FROM ad_slots s
            LEFT JOIN (
              SELECT slot_id, COUNT(1) AS total_clicks
              FROM ad_click_events
              GROUP BY slot_id
            ) total ON total.slot_id = s.id
            LEFT JOIN (
              SELECT slot_id, COUNT(1) AS recent_clicks
              FROM ad_click_events
              WHERE datetime(created_at) >= datetime('now', ?)
              GROUP BY slot_id
            ) recent ON recent.slot_id = s.id
            ORDER BY s.rank ASC, datetime(s.updated_at) DESC
            """,
            (f"-{lookback} day",),
        ).fetchall()

    items: List[Dict[str, Any]] = []
    for row in rows:
        slot = _slot_row_to_dict(row)
        slot["totalClicks"] = int(row["total_clicks"] or 0)
        slot["recentClicks"] = int(row["recent_clicks"] or 0)
        items.append(slot)
    return items


def upsert_ad_slots(slots: List[Dict[str, Any]]) -> int:
    _ensure_ready()
    if not slots:
        return 0

    prepared = [_normalize_slot_payload(item) for item in slots]
    now = _now_iso()
    with _connect() as conn:
        conn.executemany(
            """
            INSERT INTO ad_slots (
                id, title, subtitle, scene, audience, price_label, image_url,
                landing_type, landing_value, rank, is_active, starts_at, ends_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title=excluded.title,
                subtitle=excluded.subtitle,
                scene=excluded.scene,
                audience=excluded.audience,
                price_label=excluded.price_label,
                image_url=excluded.image_url,
                landing_type=excluded.landing_type,
                landing_value=excluded.landing_value,
                rank=excluded.rank,
                is_active=excluded.is_active,
                starts_at=excluded.starts_at,
                ends_at=excluded.ends_at,
                updated_at=excluded.updated_at
            """,
            [
                (
                    item["id"],
                    item["title"],
                    item["subtitle"] or None,
                    item["scene"] or None,
                    item["audience"] or None,
                    item["price_label"] or None,
                    item["image_url"] or None,
                    item["landing_type"] or "none",
                    item["landing_value"] or None,
                    int(item["rank"]),
                    int(item["is_active"]),
                    item["starts_at"],
                    item["ends_at"],
                    now,
                )
                for item in prepared
            ],
        )
        conn.commit()
    return len(prepared)


def set_ad_slot_active(*, slot_id: str, is_active: bool) -> bool:
    _ensure_ready()
    key = _normalize_text(slot_id, max_length=80)
    if not key:
        return False
    now = _now_iso()
    with _connect() as conn:
        cursor = conn.execute(
            """
            UPDATE ad_slots
            SET is_active = ?, updated_at = ?
            WHERE id = ?
            """,
            (1 if is_active else 0, now, key),
        )
        conn.commit()
    return int(cursor.rowcount or 0) > 0


def log_ad_click_event(
    *,
    slot_id: str,
    uid: Optional[str] = None,
    anonymous_id: Optional[str] = None,
    user_id: Optional[str] = None,
    source: str = "miniprogram_ads",
) -> None:
    _ensure_ready()
    key = _normalize_text(slot_id, max_length=80)
    if not key:
        return
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO ad_click_events (slot_id, uid, anonymous_id, user_id, source)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                key,
                _normalize_text(uid, max_length=120) or None,
                _normalize_text(anonymous_id, max_length=80) or None,
                _normalize_text(user_id, max_length=120) or None,
                _normalize_text(source, max_length=60) or "miniprogram_ads",
            ),
        )
        conn.commit()
