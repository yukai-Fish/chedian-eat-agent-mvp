from __future__ import annotations

import json
import math
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.services.parser import parse_query
from app.services.query_intent_service import extract_query_intents
from app.services.shop_repository import fetch_active_shops


_UNAVAILABLE_ENDPOINTS: set[str] = set()

_CAMPUS_CENTERS: Dict[str, Tuple[float, float]] = {
    "清水河": (30.7522, 103.9349),
    "沙河": (30.6742, 104.1003),
}

_AREA_OFFSETS: Dict[str, Tuple[float, float]] = {
    "校内": (0.0, 0.0),
    "西门": (0.0, -0.0090),
    "南门": (-0.0070, 0.0),
    "北门": (0.0070, 0.0),
    "东门": (0.0, 0.0090),
}

_REGIONAL_CENTERS: Dict[str, Tuple[float, float]] = {
    "温江": (30.6936, 103.8438),
    "红光": (30.7742, 103.8877),
    "市区": (30.6598, 104.0633),
}

_TASTE_TAG_KEYWORDS: Dict[str, List[str]] = {
    "想吃辣": ["辣", "麻辣", "香辣", "重口"],
    "清淡": ["清淡", "淡口", "少油", "不辣"],
    "重口": ["重口", "麻辣", "香辣", "烤", "炸"],
    "想吃面": ["面", "拉面", "面馆", "粉", "米线"],
    "想喝汤": ["汤", "汤面", "汤锅", "汤粉"],
}

_SCENE_TAG_KEYWORDS: Dict[str, List[str]] = {
    "一个人吃": ["一个人", "单人", "简餐", "快餐", "solo"],
}

_TIME_TAG_KEYWORDS: Dict[str, List[str]] = {
    "夜宵": ["夜宵", "宵夜", "深夜", "夜间"],
}

_QUERY_TERM_STOPWORDS: set[str] = {
    "我",
    "想",
    "想吃",
    "吃",
    "来",
    "来点",
    "推荐",
    "一下",
    "可以",
    "有没有",
    "附近",
    "一个人",
    "我们",
    "今天",
    "现在",
    "中午",
    "晚上",
    "夜宵",
    "预算",
    "元",
    "块",
}

_NEGATIVE_QUERY_PATTERN = re.compile(r"(?:不吃|不要|别吃|忌口|不太想吃)\s*([\u4e00-\u9fff]{1,8})")


def _build_auth_header() -> Tuple[Optional[str], Optional[str]]:
    # Preferred for Spark HTTP service.
    api_password = os.getenv("XFYUN_SPARKX_API_PASSWORD", "").strip()
    if not api_password:
        # Final fallback using key:secret convention.
        api_key = os.getenv("XFYUN_API_KEY", "").strip()
        api_secret = os.getenv("XFYUN_API_SECRET", "").strip()
        if api_key and api_secret:
            api_password = f"{api_key}:{api_secret}"

    if not api_password:
        return None, "Missing Spark API password. Set XFYUN_SPARKX_API_PASSWORD."

    return f"Bearer {api_password}", None


def _headers() -> Dict[str, str]:
    auth, _ = _build_auth_header()
    return {
        "Authorization": auth or "",
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json; charset=utf-8",
    }


def _to_float(value: Any) -> Optional[float]:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(num):
        return None
    return num


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius_km = 6371.0088
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    dlat = lat2_rad - lat1_rad
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlng / 2) ** 2
    return 2 * radius_km * math.asin(min(1.0, math.sqrt(a)))


def _to_int(value: Any) -> Optional[int]:
    num = _to_float(value)
    if num is None:
        return None
    return int(round(num))


def _tencent_map_api_key() -> str:
    return os.getenv("TENCENT_MAP_API_KEY", "").strip()


def _fetch_walking_metrics(
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
) -> Optional[Tuple[int, int]]:
    key = _tencent_map_api_key()
    if not key:
        return None

    endpoint = os.getenv("TENCENT_WALKING_ENDPOINT", "https://apis.map.qq.com/ws/direction/v1/walking").strip()
    if not endpoint:
        return None
    timeout = _to_float(os.getenv("TENCENT_WALKING_TIMEOUT_SECONDS")) or 1.8
    params = {
        "from": f"{origin_lat:.6f},{origin_lng:.6f}",
        "to": f"{dest_lat:.6f},{dest_lng:.6f}",
        "key": key,
    }

    try:
        with httpx.Client(timeout=timeout, trust_env=False, http2=False) as client:
            resp = client.get(endpoint, params=params)
    except httpx.RequestError:
        return None

    if resp.status_code != 200:
        return None

    try:
        data = resp.json()
    except ValueError:
        return None

    if int(data.get("status") or -1) != 0:
        return None

    result = data.get("result") if isinstance(data, dict) else None
    routes = result.get("routes") if isinstance(result, dict) else None
    if not isinstance(routes, list) or not routes:
        return None

    first = routes[0] if isinstance(routes[0], dict) else {}
    distance_m = _to_int(first.get("distance"))
    duration_s = _to_int(first.get("duration"))
    if distance_m is None or duration_s is None or distance_m < 0 or duration_s < 0:
        return None
    return distance_m, duration_s


def _apply_walking_metrics(
    scored: List[Dict[str, Any]],
    *,
    user_lat: float,
    user_lng: float,
) -> None:
    if not scored or not _tencent_map_api_key():
        return

    limit = _to_int(os.getenv("TENCENT_WALKING_CANDIDATE_LIMIT")) or 8
    limit = max(1, min(limit, 20))

    prelim = sorted(
        scored,
        key=lambda x: (
            -float(x["score"]),
            float(x["distance_sort"]),
            int(x["avg_price"]),
            str(x["id"]),
        ),
    )
    for candidate in prelim[:limit]:
        anchor = _shop_anchor_point(candidate["row"])
        if not anchor:
            continue
        metrics = _fetch_walking_metrics(user_lat, user_lng, anchor[0], anchor[1])
        if not metrics:
            continue

        distance_m, duration_s = metrics
        walking_minutes = round(duration_s / 60.0, 1)
        candidate["walking_distance_m"] = distance_m
        candidate["walking_minutes"] = walking_minutes
        # Nearby mode should prefer options that are truly reachable on foot now.
        candidate["score"] = float(candidate["score"]) + max(0.0, 1.9 - min(walking_minutes, 45.0) * 0.05)


def _normalize_area(text: Any) -> str:
    value = str(text or "").strip()
    if not value:
        return ""
    return re.sub(r"[\s·•\-_()/（）【】\[\],，]+", "", value)


def _shop_anchor_point(shop: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    lat = _to_float(shop.get("latitude"))
    lng = _to_float(shop.get("longitude"))
    if lat is not None and lng is not None and -90 <= lat <= 90 and -180 <= lng <= 180:
        return lat, lng

    campus_text = str(shop.get("campus", "")).strip()
    area_text = _normalize_area(shop.get("area", ""))

    for key, center in _CAMPUS_CENTERS.items():
        if key in campus_text:
            for area_key, offset in _AREA_OFFSETS.items():
                if area_key in area_text:
                    return center[0] + offset[0], center[1] + offset[1]
            return center

    for key, center in _REGIONAL_CENTERS.items():
        if key in campus_text or key in area_text:
            return center
    return None


def _normalize_name(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    text = re.sub(r"[\s·•\-_()/（）【】\[\]]+", "", text)
    return text


def _normalize_match_text(value: Any) -> str:
    return _normalize_name(value)


def _contains_any_keyword(text: str, keywords: List[str]) -> bool:
    target = _normalize_match_text(text)
    if not target:
        return False
    for raw in keywords:
        key = _normalize_match_text(raw)
        if key and key in target:
            return True
    return False


def _count_keyword_hits(text: str, keywords: List[str]) -> int:
    target = _normalize_match_text(text)
    if not target:
        return 0
    hits = 0
    seen: set[str] = set()
    for raw in keywords:
        key = _normalize_match_text(raw)
        if not key or key in seen:
            continue
        seen.add(key)
        if key in target:
            hits += 1
    return hits


def _extract_query_terms(query: str, query_intents: Optional[Dict[str, Any]] = None) -> List[str]:
    raw = str(query or "").strip()
    if not raw:
        return []

    terms: List[str] = []
    seen: set[str] = set()
    for part in re.findall(r"[\u4e00-\u9fff]{2,8}", raw):
        term = str(part or "").strip()
        if not term or term in _QUERY_TERM_STOPWORDS:
            continue
        norm = _normalize_match_text(term)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        terms.append(term)
        if len(terms) >= 16:
            break

    if isinstance(query_intents, dict):
        for item in (query_intents.get("category_keywords") or []):
            term = str(item or "").strip()
            if not term:
                continue
            norm = _normalize_match_text(term)
            if not norm or norm in seen:
                continue
            seen.add(norm)
            terms.append(term)
            if len(terms) >= 20:
                break
    return terms


def _extract_query_negative_keywords(query: str) -> List[str]:
    raw = str(query or "").strip()
    if not raw:
        return []
    result: List[str] = []
    seen: set[str] = set()
    for match in _NEGATIVE_QUERY_PATTERN.finditer(raw):
        keyword = str(match.group(1) or "").strip()
        if not keyword:
            continue
        keyword = re.sub(r"(太|很|比较|有点)$", "", keyword).strip()
        if not keyword:
            continue
        norm = _normalize_match_text(keyword)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        result.append(keyword)
        if len(result) >= 10:
            break
    return result


def _normalize_recommend_name(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"^[\s\d一二三四五六七八九十①②③④⑤⑥⑦⑧⑨⑩\.\-、:：【】\[\]\(\)（）]+", "", text)
    return text.strip()


def _resolve_candidate_by_name(
    recommendation_name: str,
    candidates_by_key: Dict[str, Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    clean = _normalize_recommend_name(recommendation_name)
    key = _normalize_name(clean)
    if not key:
        return None
    direct = candidates_by_key.get(key)
    if direct:
        return direct

    # Allow fuzzy contains matching for small format drifts (e.g. with prefixes/suffixes).
    for cand_key, candidate in candidates_by_key.items():
        if not cand_key:
            continue
        if key in cand_key or cand_key in key:
            return candidate
    return None


def _rank_score_to_percent(rank_score: Any) -> int:
    score = _to_float(rank_score)
    if score is None:
        return 72
    normalized = int(round(72 + score * 8.0))
    return max(40, min(99, normalized))


def _auto_reason_from_candidate(candidate: Dict[str, Any], query_intents: Dict[str, Any]) -> str:
    parts: List[str] = []
    if candidate.get("_categoryMatched"):
        parts.append("和你的核心口味诉求匹配")

    avg_price = _to_int(candidate.get("avg_price"))
    if avg_price is not None and avg_price > 0:
        parts.append(f"人均约{avg_price}元")

    if candidate.get("distance_km") is not None:
        distance = _to_float(candidate.get("distance_km"))
        if distance is not None:
            parts.append(f"距离约{distance:.1f}km")
    elif candidate.get("campus"):
        parts.append(f"位于{candidate.get('campus')}")

    tastes = str(candidate.get("tastes") or "").strip()
    if tastes:
        parts.append(f"口味偏{tastes}")

    if not parts:
        if query_intents.get("strict_category"):
            return "优先按照你的关键词做了相关性筛选。"
        return "综合预算、口味和就近性后给出的推荐。"
    return "，".join(parts[:3]) + "。"


def _build_structured_fallback_from_candidates(
    *,
    query: str,
    candidates: List[Dict[str, Any]],
    query_intents: Dict[str, Any],
    max_items: int = 6,
) -> Dict[str, Any]:
    strict_category = bool(query_intents.get("strict_category"))
    keywords = [str(item).strip() for item in (query_intents.get("category_keywords") or []) if str(item).strip()]
    keyword_text = "、".join(keywords[:4])
    cards: List[Dict[str, Any]] = []

    selected: List[Dict[str, Any]] = list(candidates or [])
    if strict_category and keywords:
        matched = [item for item in selected if item.get("_categoryMatched")]
        if matched:
            selected = matched
        else:
            selected = [item for item in selected if int(item.get("_queryTermHits") or 0) > 0]

    for item in selected[:max(0, max_items)]:
        cards.append(
            {
                "name": str(item.get("name") or "").strip(),
                "score": _rank_score_to_percent(item.get("_rankScore")),
                "reason": _auto_reason_from_candidate(item, query_intents),
                "recommend_dish": "",
                "scene_fit": str(item.get("scenes") or "").strip(),
                "warning": "",
            }
        )

    if strict_category and keywords and not cards:
        summary = f"暂未在当前可用店铺中找到与“{keyword_text}”高度相关的候选，建议换个关键词或放宽条件。"
    elif strict_category and keywords:
        summary = f"已优先按“{keyword_text}”做强相关筛选并排序。"
    else:
        summary = "已按预算、口味、距离和历史偏好综合排序。"

    return {
        "query": query,
        "summary": summary,
        "batch_size": 3,
        "total_count": len(cards),
        "recommendations": cards,
    }


def _sanitize_or_fallback_structured_answer(
    *,
    answer: str,
    query: str,
    candidates: List[Dict[str, Any]],
    query_intents: Dict[str, Any],
) -> Tuple[str, Dict[str, Any]]:
    fallback = _build_structured_fallback_from_candidates(query=query, candidates=candidates, query_intents=query_intents)
    stripped = _strip_fence(answer or "")
    if not stripped:
        return json.dumps(fallback, ensure_ascii=False), {"mode": "fallback-empty"}

    try:
        parsed = json.loads(stripped)
    except ValueError:
        return json.dumps(fallback, ensure_ascii=False), {"mode": "fallback-non-json"}

    if not isinstance(parsed, dict) or not isinstance(parsed.get("recommendations"), list):
        return json.dumps(fallback, ensure_ascii=False), {"mode": "fallback-invalid-structure"}

    strict_category = bool(query_intents.get("strict_category"))
    has_category_match = any(item.get("_categoryMatched") for item in candidates)
    candidates_by_key = {_normalize_name(item.get("name")): item for item in candidates if _normalize_name(item.get("name"))}
    used_keys: set[str] = set()
    sanitized_cards: List[Dict[str, Any]] = []
    dropped_count = 0

    for item in parsed.get("recommendations", []):
        if not isinstance(item, dict):
            dropped_count += 1
            continue
        candidate = _resolve_candidate_by_name(item.get("name"), candidates_by_key)
        if candidate is None:
            dropped_count += 1
            continue
        name = str(candidate.get("name") or "").strip()
        key = _normalize_name(name)
        if not key or key in used_keys:
            dropped_count += 1
            continue
        if strict_category and has_category_match and not candidate.get("_categoryMatched"):
            dropped_count += 1
            continue

        used_keys.add(key)
        sanitized_cards.append(
            {
                "name": name,
                "score": max(0, min(100, _to_int(item.get("score")) or _rank_score_to_percent(candidate.get("_rankScore")))),
                "reason": str(item.get("reason") or "").strip() or _auto_reason_from_candidate(candidate, query_intents),
                "recommend_dish": str(item.get("recommend_dish") or "").strip(),
                "scene_fit": str(item.get("scene_fit") or "").strip() or str(candidate.get("scenes") or "").strip(),
                "warning": str(item.get("warning") or "").strip(),
            }
        )

    for card in fallback.get("recommendations", []):
        key = _normalize_name(card.get("name"))
        if not key or key in used_keys:
            continue
        used_keys.add(key)
        sanitized_cards.append(card)
        if len(sanitized_cards) >= max(3, min(9, len(fallback.get("recommendations", [])))):
            break

    summary = str(parsed.get("summary") or "").strip() or str(fallback.get("summary") or "")
    structured = {
        "query": str(parsed.get("query") or query),
        "summary": summary,
        "batch_size": max(1, min(6, _to_int(parsed.get("batch_size")) or 3)),
        "total_count": max(len(sanitized_cards), _to_int(parsed.get("total_count")) or len(sanitized_cards)),
        "recommendations": sanitized_cards[:9],
    }
    return json.dumps(structured, ensure_ascii=False), {
        "mode": "sanitize-json",
        "dropped_count": dropped_count,
        "sanitized_count": len(structured["recommendations"]),
    }


def _normalize_preference_list(values: Any, *, limit: int = 20, max_length: int = 40) -> List[str]:
    if not isinstance(values, list):
        return []
    result: List[str] = []
    seen: set[str] = set()
    for item in values:
        text = str(item or "").strip()
        if not text:
            continue
        if len(text) > max_length:
            text = text[:max_length]
        if text in seen:
            continue
        seen.add(text)
        result.append(text)
        if len(result) >= limit:
            break
    return result


def _normalize_dislike_text(value: str) -> str:
    text = str(value or "").strip()
    text = re.sub(r"^(不吃|不要|忌口|不喜欢|不太吃)", "", text)
    return text.strip()


def _parse_budget_preference(text: str) -> Tuple[Optional[int], Optional[int], Optional[int]]:
    raw = str(text or "").strip()
    if not raw:
        return None, None, None
    nums = [int(item) for item in re.findall(r"\d{1,3}", raw)]
    if not nums:
        return None, None, None

    if ("以内" in raw) or ("以下" in raw):
        max_budget = nums[0]
        return None, max_budget, max_budget
    if ("以上" in raw) or ("起" in raw):
        min_budget = nums[0]
        return min_budget, None, min_budget
    if len(nums) >= 2:
        low = min(nums[0], nums[1])
        high = max(nums[0], nums[1])
        return low, high, int(round((low + high) / 2))

    single = nums[0]
    return None, single, single


def _effective_budget_from_preferences(
    *,
    budget_preference: str,
    taste_tags: List[str],
) -> Tuple[Optional[int], Optional[int], Optional[int]]:
    low, high, target = _parse_budget_preference(budget_preference)
    if low is not None or high is not None:
        return low, high, target

    if any("预算低" in str(tag or "") for tag in taste_tags):
        return None, 25, 22
    return None, None, None


def _collect_preference_keywords(tags: List[str], mapping: Dict[str, List[str]]) -> List[str]:
    keywords: List[str] = []
    seen: set[str] = set()
    for tag in tags:
        values = mapping.get(str(tag or "").strip(), [])
        for item in values:
            norm = _normalize_match_text(item)
            if not norm or norm in seen:
                continue
            seen.add(norm)
            keywords.append(item)
    return keywords


def _is_excluded(name: str, excluded_names: set[str]) -> bool:
    normalized = _normalize_name(name)
    if not normalized or not excluded_names:
        return False
    if normalized in excluded_names:
        return True
    return any(normalized in blocked or blocked in normalized for blocked in excluded_names)


def _candidate_shops(
    query: str,
    limit: int = 30,
    excluded_names: Optional[List[str]] = None,
    nearby_context: Optional[Dict[str, Any]] = None,
    preference_profile: Optional[Dict[str, Any]] = None,
    query_intents: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    slots = parse_query(query)
    intents = query_intents if isinstance(query_intents, dict) else extract_query_intents(query)
    query_category_keywords = [
        str(item or "").strip()
        for item in (intents.get("category_keywords") or [])
        if str(item or "").strip()
    ]
    strict_category = bool(intents.get("strict_category"))
    query_terms = _extract_query_terms(query, intents)
    query_negative_keywords = _extract_query_negative_keywords(query)
    shops = fetch_active_shops()
    excluded = {
        _normalize_name(name)
        for name in (excluded_names or [])
        if _normalize_name(name)
    }
    nearby_preferred = bool((nearby_context or {}).get("preferNearby"))
    user_lat = _to_float((nearby_context or {}).get("latitude"))
    user_lng = _to_float((nearby_context or {}).get("longitude"))
    if user_lat is None or user_lng is None or user_lat < -90 or user_lat > 90 or user_lng < -180 or user_lng > 180:
        user_lat = None
        user_lng = None
    campus_hint = str((nearby_context or {}).get("campus") or "").strip()
    area_hint = str((nearby_context or {}).get("areaHint") or "").strip()

    campus = (slots.location or "").strip()
    budget = slots.budget_max
    taste = (slots.taste or "").strip()
    scene = (slots.scene or "").strip()
    time_hint = (slots.time or "").strip()
    pref_campus = str((preference_profile or {}).get("campus") or "").strip()
    pref_taste_tags = _normalize_preference_list((preference_profile or {}).get("tasteTags"), limit=12, max_length=30)
    pref_dislikes = [
        item
        for item in (_normalize_dislike_text(text) for text in _normalize_preference_list((preference_profile or {}).get("dislikes"), limit=12, max_length=30))
        if item
    ]
    pref_budget_text = str((preference_profile or {}).get("budgetPreference") or "").strip()
    pref_budget_min, pref_budget_max, pref_budget_target = _effective_budget_from_preferences(
        budget_preference=pref_budget_text,
        taste_tags=pref_taste_tags,
    )
    pref_taste_keywords = _collect_preference_keywords(pref_taste_tags, _TASTE_TAG_KEYWORDS)
    pref_scene_keywords = _collect_preference_keywords(pref_taste_tags, _SCENE_TAG_KEYWORDS)
    pref_time_keywords = _collect_preference_keywords(pref_taste_tags, _TIME_TAG_KEYWORDS)

    scored: List[Dict[str, Any]] = []
    for item in shops:
        if _is_excluded(str(item.get("name", "")), excluded):
            continue

        shop_name = str(item.get("name", ""))
        shop_campus = str(item.get("campus", ""))
        shop_area = str(item.get("area", ""))
        shop_tastes = str(item.get("tastes", ""))
        shop_scenes = str(item.get("scenes", ""))
        shop_tags = str(item.get("tags", ""))
        shop_open_hours = str(item.get("open_hours", ""))
        shop_search_text = " ".join([shop_name, shop_campus, shop_area, shop_tastes, shop_scenes, shop_tags, shop_open_hours])
        shop_search_norm = _normalize_match_text(shop_search_text)

        if query_negative_keywords:
            blocked_by_query = False
            for keyword in query_negative_keywords:
                keyword_norm = _normalize_match_text(keyword)
                if keyword_norm and keyword_norm in shop_search_norm:
                    blocked_by_query = True
                    break
            if blocked_by_query:
                continue

        if pref_dislikes:
            blocked = False
            for dislike in pref_dislikes:
                dislike_norm = _normalize_match_text(dislike)
                if dislike_norm and dislike_norm in shop_search_norm:
                    blocked = True
                    break
            if blocked:
                continue

        score = 0.0
        category_hits = _count_keyword_hits(shop_search_text, query_category_keywords)
        category_matched = category_hits > 0
        query_term_hits = _count_keyword_hits(shop_search_text, query_terms)
        if query_category_keywords:
            if category_matched:
                score += min(4.8, 3.0 + 0.95 * (category_hits - 1))
            else:
                score -= 2.6 if strict_category else 1.2
        if query_term_hits > 0:
            score += min(2.8, 0.75 * query_term_hits)
        elif query_terms:
            score -= 0.55 if not strict_category else 0.95

        if campus and campus in shop_campus:
            score += 3.0
        elif pref_campus:
            if pref_campus in shop_campus:
                score += 1.8
            else:
                score -= 0.45

        avg_price = int(item.get("avg_price", 0) or 0)
        effective_budget_max = budget if budget is not None else pref_budget_max
        if effective_budget_max is not None:
            if avg_price <= effective_budget_max:
                score += 2.6 if budget is not None else 1.8
            else:
                overflow_ratio = (avg_price - effective_budget_max) / max(1, effective_budget_max)
                if budget is not None:
                    score += max(0.0, 1.0 - overflow_ratio)
                else:
                    score -= min(2.0, overflow_ratio * 2.3)

        if budget is None and pref_budget_min is not None and avg_price < pref_budget_min:
            score -= min(1.2, (pref_budget_min - avg_price) / max(1, pref_budget_min))
        if budget is None and pref_budget_target is not None:
            score += max(0.0, 0.9 - abs(avg_price - pref_budget_target) / max(8, pref_budget_target))

        if taste and taste in shop_tastes:
            score += 1.6
        if scene and scene in shop_scenes:
            score += 1.3
        if time_hint and time_hint in shop_open_hours:
            score += 0.6
        if pref_taste_keywords:
            taste_match_count = sum(1 for keyword in pref_taste_keywords if _contains_any_keyword(shop_search_text, [keyword]))
            if taste_match_count > 0:
                score += min(2.2, 0.75 * taste_match_count) if not taste else min(0.8, 0.3 * taste_match_count)
        if not scene and pref_scene_keywords and _contains_any_keyword(shop_scenes + "|" + shop_tags, pref_scene_keywords):
            score += 0.8
        if not time_hint and pref_time_keywords and _contains_any_keyword(shop_open_hours + "|" + shop_tags + "|" + shop_scenes, pref_time_keywords):
            score += 0.6

        distance_km: Optional[float] = None
        if user_lat is not None and user_lng is not None:
            anchor = _shop_anchor_point(item)
            if anchor:
                distance_km = _haversine_km(user_lat, user_lng, anchor[0], anchor[1])

        if nearby_preferred:
            if campus_hint:
                if campus_hint in shop_campus:
                    score += 2.2
                else:
                    score -= 0.9
            if area_hint and area_hint in shop_area:
                score += 0.7
            if distance_km is not None:
                # Encourage options that are likely walkable right now.
                score += max(0.0, 1.6 - min(distance_km, 8.0) * 0.28)

        distance_sort = float(distance_km) if distance_km is not None else 999.0
        scored.append(
            {
                "score": score,
                "distance_sort": distance_sort,
                "row": item,
                "distance_km": distance_km,
                "walking_minutes": None,
                "walking_distance_m": None,
                "avg_price": int(item.get("avg_price", 0) or 0),
                "id": str(item.get("id", "")),
                "category_matched": category_matched,
                "category_hits": category_hits,
                "query_term_hits": query_term_hits,
            }
        )

    if query_category_keywords:
        matched_only = [item for item in scored if item.get("category_matched")]
        if strict_category:
            if matched_only:
                # For clear "I want X" intents, keep strongly related candidates first to avoid noisy drift.
                scored = matched_only
            else:
                lexical_related = [item for item in scored if int(item.get("query_term_hits") or 0) > 0]
                if lexical_related:
                    scored = lexical_related
                else:
                    scored = []

    if nearby_preferred and user_lat is not None and user_lng is not None:
        _apply_walking_metrics(scored, user_lat=user_lat, user_lng=user_lng)

    if nearby_preferred:
        scored.sort(
            key=lambda x: (
                -float(x["score"]),
                float(x["walking_minutes"]) if x["walking_minutes"] is not None else 9999.0,
                float(x["distance_sort"]),
                int(x["avg_price"]),
                str(x["id"]),
            )
        )
    else:
        scored.sort(key=lambda x: (-float(x["score"]), int(x["avg_price"]), str(x["id"])))
    selected = scored[:limit]

    return [
        {
            "id": str(item["row"].get("id", "")),
            "name": str(item["row"].get("name", "")),
            "campus": str(item["row"].get("campus", "")),
            "area": str(item["row"].get("area", "")),
            "latitude": _to_float(item["row"].get("latitude")),
            "longitude": _to_float(item["row"].get("longitude")),
            "avg_price": int(item["row"].get("avg_price", 0) or 0),
            "open_hours": str(item["row"].get("open_hours", "")),
            "tastes": str(item["row"].get("tastes", "")),
            "scenes": str(item["row"].get("scenes", "")),
            "tags": str(item["row"].get("tags", "")),
            "distance_km": round(float(item["distance_km"]), 2) if item["distance_km"] is not None else None,
            "walking_minutes": item["walking_minutes"],
            "walking_distance_m": item["walking_distance_m"],
            "_rankScore": round(float(item["score"]), 4),
            "_categoryMatched": bool(item.get("category_matched")),
            "_categoryHits": int(item.get("category_hits") or 0),
            "_queryTermHits": int(item.get("query_term_hits") or 0),
        }
        for item in selected
    ]


def _messages(
    query: str,
    shops: List[Dict[str, Any]],
    user_profile: Optional[Dict[str, Any]] = None,
    preference_profile: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, str]]:
    system_prompt = """
You are a ranking assistant for a campus food recommendation app.
Return STRICT JSON only (no markdown, no extra text) with this shape:
{
  "query": "<original query>",
  "summary": "<one sentence recommendation strategy in Chinese>",
  "batch_size": 3,
  "total_count": <int>,
  "recommendations": [
    {
      "name": "...",
      "score": 0-100,
      "reason": "...",
      "recommend_dish": "...",
      "scene_fit": "...",
      "warning": "..."
    }
  ]
}
Rules:
1) Use shop names only from provided candidates.
2) Sort by score descending.
3) Output at most 9 recommendations.
4) If a field is unknown, use empty string.
""".strip()

    profile_summary = ""
    profile_signals = {}
    if isinstance(user_profile, dict):
        profile_summary = str(user_profile.get("summary") or "").strip()
        profile_signals = user_profile.get("signals") if isinstance(user_profile.get("signals"), dict) else {}
    preference_text = ""
    if isinstance(preference_profile, dict):
        preference_text = json.dumps(preference_profile, ensure_ascii=False)

    user_prompt = (
        f"User query: {query}\n\n"
        f"Iterative profile summary: {profile_summary or 'N/A'}\n"
        f"Iterative profile signals(JSON): {json.dumps(profile_signals, ensure_ascii=False)}\n\n"
        f"User preference profile(JSON): {preference_text or 'N/A'}\n\n"
        f"Candidates(JSON):\n{json.dumps(shops, ensure_ascii=False)}"
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _extract_content(data: Dict[str, Any]) -> str:
    choices = data.get("choices") or []
    if not choices:
        return ""
    first = choices[0] or {}
    message = first.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return content
    if isinstance(message, str):
        return message
    text = first.get("text")
    if isinstance(text, str):
        return text
    delta = first.get("delta") or {}
    if isinstance(delta, dict):
        content = delta.get("content")
        if isinstance(content, str):
            return content
    return ""


def _strip_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    return stripped.strip()


def _endpoints() -> List[str]:
    primary = os.getenv("XFYUN_SPARKX2_ENDPOINT", "https://spark-api-open.xf-yun.com/x2/chat/completions").strip()
    backup = os.getenv("XFYUN_SPARKX15_ENDPOINT", "https://spark-api-open.xf-yun.com/v2/chat/completions").strip()
    values = [primary]
    if backup and backup not in values:
        values.append(backup)
    values = [url for url in values if url and url not in _UNAVAILABLE_ENDPOINTS]
    if not values:
        values = [primary]
    return values


def _is_no_route(resp_text: str) -> bool:
    text = (resp_text or "").lower()
    return "no category route found" in text or "enginecode=10404" in text


def ask_spark_local_recommend(
    *,
    query: str,
    uid: Optional[str] = None,
    user_profile: Optional[Dict[str, Any]] = None,
    preference_profile: Optional[Dict[str, Any]] = None,
    exclude_store_names: Optional[List[str]] = None,
    nearby_context: Optional[Dict[str, Any]] = None,
    timeout_seconds: Optional[float] = None,
) -> Dict[str, Any]:
    auth, auth_err = _build_auth_header()
    if auth_err:
        return {"ok": False, "error": auth_err, "code": None, "raw": {"source": "spark-local"}}

    timeout = timeout_seconds or float(os.getenv("XFYUN_TIMEOUT_SECONDS", "25"))
    temperature = float(os.getenv("XFYUN_SPARKX_TEMPERATURE", "0.3"))
    max_tokens = int(os.getenv("XFYUN_SPARKX_MAX_TOKENS", "1800"))
    model = os.getenv("XFYUN_SPARKX_MODEL", "spark-x").strip() or "spark-x"
    thinking_mode = os.getenv("XFYUN_SPARKX_THINKING", "disabled").strip().lower() or "disabled"
    if thinking_mode not in {"enabled", "disabled", "auto"}:
        thinking_mode = "disabled"

    query_intents = extract_query_intents(query)
    shops = _candidate_shops(
        query,
        limit=30,
        excluded_names=exclude_store_names,
        nearby_context=nearby_context,
        preference_profile=preference_profile,
        query_intents=query_intents,
    )
    if not shops:
        fallback = _build_structured_fallback_from_candidates(query=query, candidates=[], query_intents=query_intents)
        return {
            "ok": True,
            "answer": json.dumps(fallback, ensure_ascii=False),
            "finishReason": "stop",
            "raw": {
                "source": "spark-local",
                "model_skipped": True,
                "skip_reason": "no_candidates_after_ranking",
                "candidate_count": 0,
                "model": model,
                "query_intents": query_intents,
                "excluded_store_names": exclude_store_names or [],
                "nearby_context": nearby_context or {},
            },
        }

    payload = {
        "model": model,
        "messages": _messages(query, shops, user_profile, preference_profile),
        "stream": False,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "user": uid or "web-user",
        "thinking": {"type": thinking_mode},
    }

    headers = _headers()
    headers["Authorization"] = auth

    attempts: List[Dict[str, Any]] = []
    last_status: Optional[int] = None
    last_text: Optional[str] = None
    chosen_endpoint: Optional[str] = None
    parsed: Optional[Dict[str, Any]] = None

    for endpoint in _endpoints():
        try:
            with httpx.Client(timeout=timeout, trust_env=False, http2=False) as client:
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                resp = client.post(endpoint, headers=headers, content=body)
        except httpx.RequestError as exc:
            attempts.append({"endpoint": endpoint, "ok": False, "request_error": str(exc)})
            continue

        last_status = resp.status_code
        last_text = resp.text
        if resp.status_code != 200:
            attempts.append({"endpoint": endpoint, "ok": False, "status_code": resp.status_code, "response_text": resp.text[:360]})
            if _is_no_route(resp.text):
                _UNAVAILABLE_ENDPOINTS.add(endpoint)
            continue

        try:
            data = resp.json()
        except ValueError:
            attempts.append({"endpoint": endpoint, "ok": False, "status_code": resp.status_code, "response_text": resp.text[:360]})
            continue

        content = _strip_fence(_extract_content(data))
        if not content:
            attempts.append({"endpoint": endpoint, "ok": False, "reason": "missing_content"})
            continue

        parsed = data
        chosen_endpoint = endpoint
        break

    if parsed is None:
        return {
            "ok": False,
            "error": f"Spark HTTP error: {last_status}" if last_status else "Spark request failed.",
            "code": last_status,
            "raw": {
                "source": "spark-local",
                "endpoint": chosen_endpoint,
                "candidate_count": len(shops),
                "attempts": attempts,
                "response_text": last_text,
                "model": model,
            },
        }

    answer = _strip_fence(_extract_content(parsed))
    if not answer:
        return {
            "ok": False,
            "error": "Spark response missing content.",
            "code": None,
            "raw": {
                "source": "spark-local",
                "endpoint": chosen_endpoint,
                "candidate_count": len(shops),
                "attempts": attempts,
                "upstream": parsed,
                "model": model,
            },
        }

    sanitized_answer, sanitize_meta = _sanitize_or_fallback_structured_answer(
        answer=answer,
        query=query,
        candidates=shops,
        query_intents=query_intents,
    )
    sid = parsed.get("sid") or parsed.get("id")
    return {
        "ok": True,
        "answer": sanitized_answer,
        "finishReason": "stop",
        "raw": {
            "source": "spark-local",
            "sid": sid,
            "id": parsed.get("id"),
            "endpoint": chosen_endpoint,
            "candidate_count": len(shops),
            "attempts": attempts,
            "usage": parsed.get("usage"),
            "model": model,
            "profile_summary": str((user_profile or {}).get("summary") or ""),
            "preference_profile": preference_profile or {},
            "query_intents": query_intents,
            "sanitize_meta": sanitize_meta,
            "raw_answer_preview": answer[:500],
            "excluded_store_names": exclude_store_names or [],
            "nearby_context": nearby_context or {},
            "upstream": parsed,
        },
    }
