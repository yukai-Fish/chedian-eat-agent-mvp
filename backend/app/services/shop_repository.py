import csv
import difflib
import hashlib
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

import httpx


BASE_DIR = Path(__file__).resolve().parents[2]
DB_PATH = Path(os.getenv("SQLITE_DB_PATH", str(BASE_DIR / "data" / "chedian.db")))
SCHEMA_PATH = BASE_DIR / "data" / "schema.sql"
SEED_CSV_PATH = BASE_DIR / "data" / "shops_mock.csv"

_init_lock = Lock()
_initialized = False
_poi_cache_lock = Lock()
_poi_detail_cache: Dict[str, Dict[str, Any]] = {}

TEST_SEED_SHOPS = [
    {
        "id": "s001",
        "name": "韩式拌饭屋",
        "campus": "清水河",
        "area": "校内",
        "avg_price": 30,
        "open_hours": "10:00-22:00",
        "tastes": "辣|清淡",
        "scenes": "同学聚餐|一个人",
        "tags": "韩式|拌饭",
        "is_open": 1,
    },
    {
        "id": "s002",
        "name": "粤式烧腊饭",
        "campus": "清水河",
        "area": "西门",
        "avg_price": 30,
        "open_hours": "10:30-21:00",
        "tastes": "清淡",
        "scenes": "一个人|同学聚餐",
        "tags": "粤式|烧腊",
        "is_open": 1,
    },
    {
        "id": "s003",
        "name": "川味小馆",
        "campus": "清水河",
        "area": "南门",
        "avg_price": 30,
        "open_hours": "11：00-23：00",
        "tastes": "辣",
        "scenes": "同学聚餐",
        "tags": "川菜|家常菜",
        "is_open": 1,
    },
    {
        "id": "s004",
        "name": "番茄牛腩粉",
        "campus": "沙河",
        "area": "校内",
        "avg_price": 20,
        "open_hours": "10:30-21:00",
        "tastes": "清淡",
        "scenes": "一个人",
        "tags": "粉面|清淡",
        "is_open": 1,
    },
    {
        "id": "s005",
        "name": "深夜小串",
        "campus": "清水河",
        "area": "西门",
        "avg_price": 40,
        "open_hours": "18:00-03:00",
        "tastes": "辣",
        "scenes": "同学聚餐",
        "tags": "烧烤|夜宵",
        "is_open": 1,
    },
    {
        "id": "s006",
        "name": "北方面馆",
        "campus": "清水河",
        "area": "南门",
        "avg_price": 18,
        "open_hours": "07:00-21:00",
        "tastes": "清淡|辣",
        "scenes": "一个人|同学聚餐",
        "tags": "面馆|北方",
        "is_open": 1,
    },
    {
        "id": "s007",
        "name": "清真牛肉面",
        "campus": "清水河",
        "area": "西门",
        "avg_price": 28,
        "open_hours": "09:00-22:00",
        "tastes": "清淡",
        "scenes": "一个人|同学聚餐",
        "tags": "清真|面馆",
        "is_open": 1,
    },
    {
        "id": "s008",
        "name": "轻食能量碗",
        "campus": "沙河",
        "area": "校内",
        "avg_price": 26,
        "open_hours": "10:00-20:00",
        "tastes": "清淡",
        "scenes": "一个人",
        "tags": "轻食|健康餐",
        "is_open": 1,
    },
]


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(schema_sql)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS app_meta (
          key TEXT PRIMARY KEY,
          value TEXT
        )
        """
    )


def _table_has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(str(row["name"]) == column for row in rows)


def _ensure_compat_columns(conn: sqlite3.Connection) -> None:
    if not _table_has_column(conn, "shops", "poi_id"):
        conn.execute("ALTER TABLE shops ADD COLUMN poi_id TEXT")
    if not _table_has_column(conn, "shops", "address"):
        conn.execute("ALTER TABLE shops ADD COLUMN address TEXT")
    if not _table_has_column(conn, "shops", "category"):
        conn.execute("ALTER TABLE shops ADD COLUMN category TEXT")
    if not _table_has_column(conn, "shops", "phone"):
        conn.execute("ALTER TABLE shops ADD COLUMN phone TEXT")
    if not _table_has_column(conn, "shops", "image_urls"):
        conn.execute("ALTER TABLE shops ADD COLUMN image_urls TEXT")
    if not _table_has_column(conn, "shops", "geo_source"):
        conn.execute("ALTER TABLE shops ADD COLUMN geo_source TEXT")
    if not _table_has_column(conn, "shops", "geo_score"):
        conn.execute("ALTER TABLE shops ADD COLUMN geo_score REAL")

    if not _table_has_column(conn, "shops", "latitude"):
        conn.execute("ALTER TABLE shops ADD COLUMN latitude REAL")
    if not _table_has_column(conn, "shops", "longitude"):
        conn.execute("ALTER TABLE shops ADD COLUMN longitude REAL")

    if not _table_has_column(conn, "usage_events", "anonymous_id"):
        conn.execute("ALTER TABLE usage_events ADD COLUMN anonymous_id TEXT")
    if not _table_has_column(conn, "usage_events", "user_id"):
        conn.execute("ALTER TABLE usage_events ADD COLUMN user_id TEXT")

    if not _table_has_column(conn, "feedback_submissions", "anonymous_id"):
        conn.execute("ALTER TABLE feedback_submissions ADD COLUMN anonymous_id TEXT")
    if not _table_has_column(conn, "feedback_submissions", "user_id"):
        conn.execute("ALTER TABLE feedback_submissions ADD COLUMN user_id TEXT")


def _seed_signature() -> str:
    data = SEED_CSV_PATH.read_bytes()
    return hashlib.sha256(data).hexdigest()


def _meta_get(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM app_meta WHERE key = ?", (key,)).fetchone()
    if not row:
        return None
    return str(row["value"]) if row["value"] is not None else None


def _meta_set(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        """
        INSERT INTO app_meta(key, value)
        VALUES(?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
        """,
        (key, value),
    )


def _parse_coordinate(value: Any, *, min_value: float = -180, max_value: float = 180) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        num = float(text)
    except (TypeError, ValueError):
        return None
    if not (min_value <= num <= max_value):
        return None
    return num


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _split_values(text: str) -> List[str]:
    return [item.strip() for item in re.split(r"[|,;/\n]+", text or "") if item.strip()]


def _normalize_phone(text: str) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    parts = [item.strip() for item in re.split(r"[;,/]\s*", raw) if item.strip()]
    if not parts:
        return raw
    unique: List[str] = []
    seen: set[str] = set()
    for item in parts:
        if item in seen:
            continue
        seen.add(item)
        unique.append(item)
    return " / ".join(unique)


def _time_to_minutes(text: str) -> Optional[int]:
    cleaned = (text or "").strip().replace("：", ":")
    m = re.fullmatch(r"(\d{1,2})\s*:\s*(\d{1,2})", cleaned)
    if not m:
        return None
    hh = int(m.group(1))
    mm = int(m.group(2))
    if hh < 0 or hh > 24 or mm < 0 or mm > 59:
        return None
    if hh == 24 and mm != 0:
        return None
    return hh * 60 + mm


def _parse_open_intervals(open_hours: str) -> List[Tuple[int, int]]:
    text = str(open_hours or "").strip()
    if not text:
        return []

    normalized = (
        text.replace("：", ":")
        .replace("，", ",")
        .replace("；", ";")
        .replace("~", "-")
        .replace("—", "-")
        .replace("–", "-")
        .replace("至", "-")
        .replace("到", "-")
    )
    lowered = normalized.lower()
    if "24小时" in normalized or "全天" in normalized or "24h" in lowered:
        return [(0, 24 * 60)]

    intervals: List[Tuple[int, int]] = []
    for start_text, end_text in re.findall(r"(\d{1,2}\s*:\s*\d{1,2})\s*-\s*(\d{1,2}\s*:\s*\d{1,2})", normalized):
        start = _time_to_minutes(start_text)
        end = _time_to_minutes(end_text)
        if start is None or end is None:
            continue
        if end <= start:
            end += 24 * 60
        intervals.append((start, end))

    if intervals:
        return intervals

    points = [_time_to_minutes(token) for token in re.findall(r"\d{1,2}\s*:\s*\d{1,2}", normalized)]
    points = [item for item in points if item is not None]
    for idx in range(0, len(points) - 1, 2):
        start = points[idx]
        end = points[idx + 1]
        if end <= start:
            end += 24 * 60
        intervals.append((start, end))
    return intervals


def _minutes_to_hhmm(minutes_value: int) -> str:
    value = int(minutes_value) % (24 * 60)
    hh = value // 60
    mm = value % 60
    return f"{hh:02d}:{mm:02d}"


def _compute_business_status(open_hours: str) -> Dict[str, str]:
    now = datetime.now().astimezone()
    evaluated_at = now.isoformat(timespec="seconds")
    intervals = _parse_open_intervals(open_hours)
    if not intervals:
        return {
            "code": "unknown",
            "label": "营业时间待补充",
            "detail": "暂无营业时间，建议先看近期评价后再决定。",
            "evaluatedAt": evaluated_at,
        }

    now_minute = now.hour * 60 + now.minute
    is_open = False
    close_in: Optional[int] = None
    close_at: Optional[int] = None

    for start, end in intervals:
        for probe in (now_minute, now_minute + 24 * 60):
            if start <= probe < end:
                left = end - probe
                if close_in is None or left < close_in:
                    is_open = True
                    close_in = left
                    close_at = end

    if is_open:
        if close_in is not None and close_in <= 60:
            return {
                "code": "closing",
                "label": "即将打烊",
                "detail": f"约 {max(1, close_in)} 分钟后打烊（{_minutes_to_hhmm(close_at or 0)}）",
                "evaluatedAt": evaluated_at,
            }
        return {
            "code": "open",
            "label": "营业中",
            "detail": f"当前可到店（预计 {_minutes_to_hhmm(close_at or 0)} 前营业）",
            "evaluatedAt": evaluated_at,
        }

    next_open_in: Optional[int] = None
    next_open_at: Optional[int] = None
    for start, _end in intervals:
        for probe_start in (start, start + 24 * 60):
            delta = probe_start - now_minute
            if delta <= 0:
                continue
            if next_open_in is None or delta < next_open_in:
                next_open_in = delta
                next_open_at = probe_start

    if next_open_in is None:
        return {
            "code": "closed",
            "label": "休息中",
            "detail": "当前不在营业时段。",
            "evaluatedAt": evaluated_at,
        }

    return {
        "code": "closed",
        "label": "休息中",
        "detail": f"约 {next_open_in} 分钟后营业（{_minutes_to_hhmm(next_open_at or 0)}）",
        "evaluatedAt": evaluated_at,
    }


def _derive_price_band(avg_price: int) -> Tuple[int, int]:
    price = max(1, int(avg_price or 1))
    span = max(4, min(20, int(round(price * 0.3))))
    low = max(1, price - span)
    high = max(low + 2, price + span)
    return low, high


def _tencent_map_api_key() -> str:
    return os.getenv("TENCENT_MAP_API_KEY", "").strip()


def _fetch_poi_detail_from_tencent(poi_id: str) -> Dict[str, Any]:
    key = _tencent_map_api_key()
    if not key or not poi_id:
        return {}

    endpoint = os.getenv("TENCENT_PLACE_DETAIL_ENDPOINT", "https://apis.map.qq.com/ws/place/v1/detail").strip()
    timeout = float(os.getenv("TENCENT_PLACE_DETAIL_TIMEOUT_SECONDS", "2.2"))
    if not endpoint:
        return {}

    params = {"id": poi_id, "key": key}
    try:
        with httpx.Client(timeout=timeout, trust_env=False, http2=False) as client:
            resp = client.get(endpoint, params=params)
    except httpx.RequestError:
        return {}
    if resp.status_code != 200:
        return {}

    try:
        data = resp.json()
    except ValueError:
        return {}

    if int(data.get("status") or -1) != 0:
        return {}
    result = data.get("result")
    return result if isinstance(result, dict) else {}


def _fetch_poi_detail_cached(poi_id: str) -> Dict[str, Any]:
    key = str(poi_id or "").strip()
    if not key:
        return {}
    with _poi_cache_lock:
        if key in _poi_detail_cache:
            return dict(_poi_detail_cache[key])

    data = _fetch_poi_detail_from_tencent(key)
    with _poi_cache_lock:
        _poi_detail_cache[key] = dict(data)
    return dict(data)


def _extract_poi_photo_urls(poi_detail: Dict[str, Any]) -> List[str]:
    candidates: List[str] = []
    for bucket_key in ("photos", "photo", "images", "image_urls"):
        value = poi_detail.get(bucket_key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    candidates.append(item)
                elif isinstance(item, dict):
                    for url_key in ("url", "photo_url", "src"):
                        url_value = item.get(url_key)
                        if isinstance(url_value, str):
                            candidates.append(url_value)
                            break
        elif isinstance(value, str):
            candidates.extend(_split_values(value))

    urls: List[str] = []
    seen: set[str] = set()
    for raw in candidates:
        text = str(raw or "").strip()
        if not text or not (text.startswith("http://") or text.startswith("https://")):
            continue
        if text in seen:
            continue
        seen.add(text)
        urls.append(text)
    return urls


def _build_static_map_image_urls(latitude: Optional[float], longitude: Optional[float]) -> List[str]:
    if latitude is None or longitude is None:
        return []
    key = _tencent_map_api_key()
    if not key:
        return []

    base = "https://apis.map.qq.com/ws/staticmap/v2/"
    urls: List[str] = []
    for zoom in (17, 15):
        query = urlencode(
            {
                "center": f"{latitude:.6f},{longitude:.6f}",
                "zoom": str(zoom),
                "size": "960*520",
                "scale": "2",
                "maptype": "roadmap",
                "markers": f"size:large|color:0xC89B44|label:S|{latitude:.6f},{longitude:.6f}",
                "key": key,
            }
        )
        urls.append(f"{base}?{query}")
    return urls


def _seed_from_csv_if_needed(conn: sqlite3.Connection) -> None:
    # Keep tests deterministic regardless of external CSV churn.
    if os.getenv("PYTEST_CURRENT_TEST") or os.getenv("CHEDIAN_USE_TEST_SEED") == "1":
        conn.execute("DELETE FROM shops")
        conn.executemany(
            """
            INSERT INTO shops (
                id, name, campus, area, poi_id, address, category, phone, image_urls, geo_source, geo_score, latitude, longitude, avg_price, open_hours, tastes, scenes, tags, is_open
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    item["id"],
                    item["name"],
                    item["campus"],
                    item["area"],
                    str(item.get("poi_id") or "").strip() or None,
                    str(item.get("address") or "").strip() or None,
                    str(item.get("category") or "").strip() or None,
                    _normalize_phone(str(item.get("phone") or "")) or None,
                    "|".join(_split_values(str(item.get("image_urls") or ""))) or None,
                    str(item.get("geo_source") or "").strip() or None,
                    _parse_coordinate(item.get("geo_score"), min_value=-1000000, max_value=1000000),
                    _parse_coordinate(item.get("latitude"), min_value=-90, max_value=90),
                    _parse_coordinate(item.get("longitude"), min_value=-180, max_value=180),
                    int(item["avg_price"]),
                    item["open_hours"],
                    item["tastes"],
                    item["scenes"],
                    item["tags"],
                    int(item["is_open"]),
                )
                for item in TEST_SEED_SHOPS
            ],
        )
        _meta_set(conn, "shops_seed_signature", "test-seed-v1")
        _meta_set(conn, "shops_seed_count", str(len(TEST_SEED_SHOPS)))
        return

    with open(SEED_CSV_PATH, "r", encoding="utf-8-sig") as f:
        records = list(csv.DictReader(f))

    desired_signature = _seed_signature()
    current_signature = _meta_get(conn, "shops_seed_signature")
    row = conn.execute("SELECT COUNT(1) AS cnt FROM shops").fetchone()
    current_count = int(row["cnt"]) if row else 0

    if current_count > 0 and current_signature == desired_signature:
        return

    conn.execute("DELETE FROM shops")
    conn.executemany(
        """
        INSERT INTO shops (
            id, name, campus, area, poi_id, address, category, phone, image_urls, geo_source, geo_score, latitude, longitude, avg_price, open_hours, tastes, scenes, tags, is_open
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                item["id"],
                item["name"],
                item["campus"],
                item.get("area", ""),
                str(item.get("poi_id") or "").strip() or None,
                str(item.get("address") or "").strip() or None,
                str(item.get("category") or "").strip() or None,
                _normalize_phone(str(item.get("phone") or "")) or None,
                "|".join(_split_values(str(item.get("image_urls") or ""))) or None,
                str(item.get("geo_source") or "").strip() or None,
                _parse_coordinate(item.get("geo_score"), min_value=-1000000, max_value=1000000),
                _parse_coordinate(item.get("latitude"), min_value=-90, max_value=90),
                _parse_coordinate(item.get("longitude"), min_value=-180, max_value=180),
                int(item["avg_price"]),
                item.get("open_hours", ""),
                item.get("tastes", ""),
                item.get("scenes", ""),
                item.get("tags", ""),
                int(item.get("is_open", 1)),
            )
            for item in records
        ],
    )
    _meta_set(conn, "shops_seed_signature", desired_signature)
    _meta_set(conn, "shops_seed_count", str(len(records)))


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
            _seed_from_csv_if_needed(conn)
            conn.commit()
        _initialized = True


def fetch_active_shops() -> List[Dict]:
    ensure_database()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, name, campus, area, poi_id, address, category, phone, image_urls, geo_source, geo_score, latitude, longitude, avg_price, open_hours, tastes, scenes, tags, is_open
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


def _split_tag_text(text: str) -> List[str]:
    return [item.strip() for item in re.split(r"[|,;/]+", text or "") if item.strip()]


def _normalize_store_name(name: str) -> str:
    text = (name or "").strip()
    if not text:
        return ""
    # Remove bracketed area notes, punctuation, and common suffix words.
    text = re.sub(r"[\(（【\[].*?[\)）】\]]", "", text)
    text = re.sub(r"[\s·•\-_/]+", "", text)
    text = re.sub(r"(餐厅|饭店|店|食堂|美食城)$", "", text)
    return text


def _name_similarity(query: str, candidate: str) -> float:
    q = _normalize_store_name(query)
    c = _normalize_store_name(candidate)
    if not q or not c:
        return 0.0
    if q == c:
        return 1.0

    ratio = difflib.SequenceMatcher(None, q, c).ratio()
    qset = set(q)
    cset = set(c)
    overlap = len(qset & cset) / max(1, len(qset | cset))
    contain_bonus = 0.12 if (q in c or c in q) else 0.0
    prefix_bonus = 0.08 if (c.startswith(q) or q.startswith(c)) else 0.0
    return min(1.0, 0.62 * ratio + 0.30 * overlap + contain_bonus + prefix_bonus)


def _fuzzy_find_store_row(conn: sqlite3.Connection, store_name: str) -> Optional[sqlite3.Row]:
    rows = conn.execute(
        """
        SELECT id, name, campus, area, poi_id, address, category, phone, image_urls, geo_source, geo_score, latitude, longitude, avg_price, open_hours, tastes, scenes, tags
        FROM shops
        WHERE is_open = 1
        """
    ).fetchall()
    if not rows:
        return None

    scored = sorted(
        ((float(_name_similarity(store_name, str(row["name"] or ""))), row) for row in rows),
        key=lambda x: x[0],
        reverse=True,
    )
    best_score, best_row = scored[0]
    # Conservative threshold to avoid clearly wrong jumps.
    return best_row if best_score >= 0.60 else None


def _fetch_store_row(conn: sqlite3.Connection, store_name: str) -> Optional[sqlite3.Row]:
    exact = conn.execute(
        """
        SELECT id, name, campus, area, poi_id, address, category, phone, image_urls, geo_source, geo_score, latitude, longitude, avg_price, open_hours, tastes, scenes, tags
        FROM shops
        WHERE is_open = 1 AND name = ?
        LIMIT 1
        """,
        (store_name,),
    ).fetchone()
    if exact:
        return exact

    like_row = conn.execute(
        """
        SELECT id, name, campus, area, poi_id, address, category, phone, image_urls, geo_source, geo_score, latitude, longitude, avg_price, open_hours, tastes, scenes, tags
        FROM shops
        WHERE is_open = 1 AND name LIKE ?
        ORDER BY CASE WHEN name LIKE ? THEN 0 ELSE 1 END, avg_price ASC
        LIMIT 1
        """,
        (f"%{store_name}%", f"{store_name}%"),
    ).fetchone()
    if like_row:
        return like_row

    return _fuzzy_find_store_row(conn, store_name)


def fetch_store_detail_by_name(store_name: str) -> Optional[Dict[str, Any]]:
    ensure_database()
    key = (store_name or "").strip()
    if not key:
        return None

    with _connect() as conn:
        shop_row = _fetch_store_row(conn, key)
        if not shop_row:
            return None

        review_rows = conn.execute(
            """
            SELECT id, rating, comment, recommend_dish, recommend_reason, source, created_at
            FROM feedback_submissions
            WHERE store_name = ?
               OR store_name LIKE ?
            ORDER BY datetime(created_at) DESC, id DESC
            LIMIT 20
            """,
            (shop_row["name"], f"%{shop_row['name']}%"),
        ).fetchall()

    latitude = float(shop_row["latitude"]) if shop_row["latitude"] is not None else None
    longitude = float(shop_row["longitude"]) if shop_row["longitude"] is not None else None
    poi_id = str(shop_row["poi_id"] or "").strip()
    poi_detail = _fetch_poi_detail_cached(poi_id) if poi_id else {}

    raw_phone = _normalize_phone(str(shop_row["phone"] or ""))
    detail_phone = _normalize_phone(
        str(poi_detail.get("tel") or poi_detail.get("phone") or poi_detail.get("telephone") or "")
    )
    phone = raw_phone or detail_phone

    image_urls: List[str] = []
    for raw in _split_values(str(shop_row["image_urls"] or "")):
        url = str(raw or "").strip()
        if not url:
            continue
        if url.startswith(("http://", "https://", "/")):
            image_urls.append(url)
    if not image_urls:
        image_urls = _extract_poi_photo_urls(poi_detail)
    if not image_urls:
        image_urls = _build_static_map_image_urls(latitude, longitude)

    avg_price = _safe_int(shop_row["avg_price"], default=0)
    avg_price_min, avg_price_max = _derive_price_band(avg_price)
    open_hours = str(shop_row["open_hours"] or "")
    business_status = _compute_business_status(open_hours)
    address = str(shop_row["address"] or "").strip() or str(poi_detail.get("address") or "").strip()
    category = str(shop_row["category"] or "").strip() or str(poi_detail.get("category") or "").strip()

    reviews: List[Dict[str, Any]] = []
    ratings: List[int] = []
    for row in review_rows:
        rating = row["rating"] if row["rating"] is not None else None
        if isinstance(rating, int):
            ratings.append(rating)
        reviews.append(
            {
                "id": int(row["id"]),
                "rating": rating,
                "comment": row["comment"],
                "recommendDish": row["recommend_dish"],
                "recommendReason": row["recommend_reason"],
                "createdAt": str(row["created_at"]),
                "source": row["source"],
            }
        )

    return {
        "id": str(shop_row["id"]),
        "name": str(shop_row["name"]),
        "campus": str(shop_row["campus"]),
        "area": str(shop_row["area"] or ""),
        "poiId": poi_id,
        "address": address,
        "category": category,
        "geoSource": str(shop_row["geo_source"] or ""),
        "phone": phone or None,
        "avgPrice": avg_price,
        "avgPriceMin": avg_price_min,
        "avgPriceMax": avg_price_max,
        "openHours": open_hours,
        "businessStatus": business_status,
        "imageUrls": image_urls,
        "categoryTags": _split_tag_text(str(shop_row["tags"] or "")),
        "tasteTags": _split_tag_text(str(shop_row["tastes"] or "")),
        "sceneTags": _split_tag_text(str(shop_row["scenes"] or "")),
        "reviews": reviews,
        "reviewCount": len(reviews),
        "avgRating": round(sum(ratings) / len(ratings), 2) if ratings else None,
    }


def resolve_shop_identity_by_name(store_name: str) -> Optional[Dict[str, Any]]:
    ensure_database()
    key = (store_name or "").strip()
    if not key:
        return None

    with _connect() as conn:
        row = _fetch_store_row(conn, key)
        if not row:
            return None
        return {
            "id": str(row["id"]),
            "name": str(row["name"]),
            "campus": str(row["campus"] or ""),
            "area": str(row["area"] or ""),
            "poi_id": str(row["poi_id"] or ""),
            "address": str(row["address"] or ""),
            "category": str(row["category"] or ""),
            "latitude": float(row["latitude"]) if row["latitude"] is not None else None,
            "longitude": float(row["longitude"]) if row["longitude"] is not None else None,
        }
