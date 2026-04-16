#!/usr/bin/env python3
from __future__ import annotations

import csv
import difflib
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

ROOT = Path(__file__).resolve().parent.parent
SHOPS_CSV = ROOT / "backend" / "data" / "shops_mock.csv"
POI_CSV = ROOT / "outputs" / "qingshuihe_restaurants_raw.csv"
REPORT_JSON = ROOT / "outputs" / "shops_enrich_report.json"
ENV_CANDIDATES = [ROOT / ".env", ROOT / "backend" / ".env"]

GEOCODER_URL = "https://apis.map.qq.com/ws/geocoder/v1/"
PLACE_SEARCH_URL = "https://apis.map.qq.com/ws/place/v1/search"


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'").strip()
        if key and key not in os.environ:
            os.environ[key] = value


def ensure_api_key() -> str:
    key = os.getenv("TENCENT_MAP_API_KEY", "").strip()
    if key:
        return key
    for p in ENV_CANDIDATES:
        _load_env_file(p)
        key = os.getenv("TENCENT_MAP_API_KEY", "").strip()
        if key:
            return key
    raise RuntimeError("TENCENT_MAP_API_KEY not configured")


def normalize_name(name: str) -> str:
    text = (name or "").strip().lower()
    if not text:
        return ""
    text = re.sub(r"[\s\-_/·・,.，。()（）\[\]【】]+", "", text)
    text = re.sub(r"(店|分店|餐厅|饭店|食堂|小吃店)$", "", text)
    return text


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").strip().lower())


def score_match(shop_name: str, poi_name: str) -> float:
    s = normalize_name(shop_name)
    p = normalize_name(poi_name)
    if not s or not p:
        return 0.0
    if s == p:
        return 1.0
    ratio = difflib.SequenceMatcher(None, s, p).ratio()
    contain_bonus = 0.14 if (s in p or p in s) else 0.0
    prefix_bonus = 0.08 if (s.startswith(p) or p.startswith(s)) else 0.0
    overlap = len(set(s) & set(p)) / max(1, len(set(s) | set(p)))
    return min(1.0, 0.62 * ratio + 0.24 * overlap + contain_bonus + prefix_bonus)


@dataclass
class PoiRow:
    source_id: str
    name: str
    address: str
    category: str
    lat: Optional[float]
    lng: Optional[float]


def to_float(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        t = str(v).strip()
        if not t:
            return None
        return float(t)
    except (TypeError, ValueError):
        return None


def load_pois() -> List[PoiRow]:
    with POI_CSV.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    out: List[PoiRow] = []
    for r in rows:
        out.append(
            PoiRow(
                source_id=str(r.get("source_id") or "").strip(),
                name=str(r.get("name") or "").strip(),
                address=str(r.get("address") or "").strip(),
                category=str(r.get("category") or "").strip(),
                lat=to_float(r.get("lat")),
                lng=to_float(r.get("lng")),
            )
        )
    return out


def best_poi_for_shop(shop_name: str, pois: List[PoiRow]) -> Tuple[Optional[PoiRow], float]:
    best: Optional[PoiRow] = None
    best_score = 0.0
    for poi in pois:
        s = score_match(shop_name, poi.name)
        if s > best_score:
            best_score = s
            best = poi
    return best, best_score


def geocode_shop(session: requests.Session, key: str, query: str) -> Dict[str, Any]:
    max_retry = 3
    for i in range(max_retry):
        resp = session.get(GEOCODER_URL, params={"address": query, "key": key}, timeout=15)
        payload = resp.json() if resp.headers.get("content-type", "").lower().find("json") >= 0 else {}
        status = int(payload.get("status", -1)) if isinstance(payload, dict) else -1

        if status == 0:
            result = payload.get("result") or {}
            loc = result.get("location") or {}
            formatted = result.get("formatted_addresses") or {}
            return {
                "ok": True,
                "lat": to_float(loc.get("lat")),
                "lng": to_float(loc.get("lng")),
                "address": str(formatted.get("recommend") or result.get("address") or "").strip(),
                "status": 0,
                "message": "ok",
            }

        if status == 120:
            time.sleep(0.5 + i * 0.2)
            continue
        if status == 121:
            return {"ok": False, "status": 121, "message": str(payload.get("message") or "daily limit")}
        return {"ok": False, "status": status, "message": str(payload.get("message") or "failed")}

    return {"ok": False, "status": 120, "message": "qps limit"}


def place_search_shop(session: requests.Session, key: str, query: str) -> Dict[str, Any]:
    max_retry = 3
    for i in range(max_retry):
        resp = session.get(
            PLACE_SEARCH_URL,
            params={
                "key": key,
                "keyword": query,
                "boundary": "region(成都,0)",
                "page_size": 5,
                "page_index": 1,
            },
            timeout=15,
        )
        payload = resp.json() if resp.headers.get("content-type", "").lower().find("json") >= 0 else {}
        status = int(payload.get("status", -1)) if isinstance(payload, dict) else -1
        if status == 0:
            items = payload.get("data") or []
            if not items:
                return {"ok": False, "status": 0, "message": "empty"}
            first = items[0] or {}
            loc = first.get("location") or {}
            return {
                "ok": True,
                "lat": to_float(loc.get("lat")),
                "lng": to_float(loc.get("lng")),
                "address": str(first.get("address") or "").strip(),
                "category": str(first.get("category") or "").strip(),
                "poi_id": str(first.get("id") or "").strip(),
                "status": 0,
                "message": "ok",
            }
        if status == 120:
            time.sleep(0.5 + i * 0.2)
            continue
        if status == 121:
            return {"ok": False, "status": 121, "message": str(payload.get("message") or "daily limit")}
        return {"ok": False, "status": status, "message": str(payload.get("message") or "failed")}
    return {"ok": False, "status": 120, "message": "qps limit"}


def enrich() -> None:
    key = ensure_api_key()
    pois = load_pois()

    with SHOPS_CSV.open("r", encoding="utf-8-sig", newline="") as f:
        shops = list(csv.DictReader(f))

    if not shops:
        raise RuntimeError("shops csv empty")

    fieldnames = list(shops[0].keys())
    for col in ["poi_id", "address", "category", "geo_source", "geo_score"]:
        if col not in fieldnames:
            insert_at = fieldnames.index("latitude") if "latitude" in fieldnames else len(fieldnames)
            fieldnames.insert(insert_at, col)

    stats = {
        "total": len(shops),
        "poi_matched": 0,
        "geocoder_success": 0,
        "geocoder_failed": 0,
        "place_search_success": 0,
        "place_search_failed": 0,
        "daily_limit_hit": False,
    }

    session = requests.Session()

    unmatched_indices: List[int] = []

    # Pass 1: POI name matching (no API quota consumption).
    for idx, row in enumerate(shops):
        name = str(row.get("name") or "").strip()

        poi, s = best_poi_for_shop(name, pois)
        if poi and s >= 0.78 and poi.lat is not None and poi.lng is not None:
            row["latitude"] = f"{poi.lat:.6f}"
            row["longitude"] = f"{poi.lng:.6f}"
            row["poi_id"] = poi.source_id
            row["address"] = poi.address
            row["category"] = poi.category
            row["geo_source"] = "poi_match"
            row["geo_score"] = f"{s:.3f}"
            stats["poi_matched"] += 1
        else:
            unmatched_indices.append(idx)

        # default keys
        row.setdefault("poi_id", "")
        row.setdefault("address", "")
        row.setdefault("category", "")

    # Pass 2: geocoder fallback for unmatched shops.
    for idx in unmatched_indices:
        row = shops[idx]
        name = str(row.get("name") or "").strip()
        campus = str(row.get("campus") or "").strip()
        area = str(row.get("area") or "").strip()

        query = f"{name} {campus} {area} 成都".strip()
        r = geocode_shop(session, key, query)
        if r.get("ok") and r.get("lat") is not None and r.get("lng") is not None:
            row["latitude"] = f"{float(r['lat']):.6f}"
            row["longitude"] = f"{float(r['lng']):.6f}"
            if not str(row.get("address") or "").strip():
                row["address"] = str(r.get("address") or "")
            row["geo_source"] = "geocoder"
            row["geo_score"] = row.get("geo_score") or "0.000"
            stats["geocoder_success"] += 1
        else:
            row["geo_source"] = row.get("geo_source") or "fallback"
            row["geo_score"] = row.get("geo_score") or "0.000"
            stats["geocoder_failed"] += 1
            if int(r.get("status") or -1) == 121:
                stats["daily_limit_hit"] = True
                break

        # Respect qps <= 5
        time.sleep(0.23)

    # Pass 3: place search fallback for still-unmatched rows.
    for row in shops:
        if str(row.get("geo_source") or "").strip() not in {"fallback", ""}:
            continue

        query = str(row.get("name") or "").strip()
        if not query:
            continue
        r = place_search_shop(session, key, query)
        if r.get("ok") and r.get("lat") is not None and r.get("lng") is not None:
            row["latitude"] = f"{float(r['lat']):.6f}"
            row["longitude"] = f"{float(r['lng']):.6f}"
            row["address"] = str(r.get("address") or row.get("address") or "")
            row["category"] = str(r.get("category") or row.get("category") or "")
            row["poi_id"] = str(r.get("poi_id") or row.get("poi_id") or "")
            row["geo_source"] = "place_search"
            row["geo_score"] = row.get("geo_score") or "0.000"
            stats["place_search_success"] += 1
        else:
            stats["place_search_failed"] += 1
            if int(r.get("status") or -1) == 121:
                stats["daily_limit_hit"] = True
                break
        time.sleep(0.23)

    with SHOPS_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(shops)

    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    enrich()
