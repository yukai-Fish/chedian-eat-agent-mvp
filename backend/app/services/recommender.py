import re
from typing import Dict, List, Tuple

from app.core.scoring_config import load_scoring_config
from app.models.schemas import ParsedSlots, ShopResult
from app.services.shop_repository import fetch_active_shops


def _parse_hhmm_to_minutes(hhmm: str) -> int:
    normalized = str(hhmm or "").strip().replace("：", ":")
    hour, minute = normalized.split(":")
    return int(hour) * 60 + int(minute)


def _normalize_time_slot_ranges(config: Dict) -> Dict[str, Tuple[int, int]]:
    result: Dict[str, Tuple[int, int]] = {}
    for key, value in config["time_slot_ranges"].items():
        start = _parse_hhmm_to_minutes(value[0])
        end = _parse_hhmm_to_minutes(value[1])
        if end <= start:
            end += 24 * 60
        result[key] = (start, end)
    return result


def _parse_open_hours(open_hours: str) -> Tuple[int, int]:
    raw = str(open_hours or "").strip()
    if not raw or raw in {"无", "全天"}:
        raise ValueError("missing or all-day text")

    # Tolerate mixed punctuation and multi-segment ranges, e.g.:
    # 11：00-13：30，17：00-20：30
    matches = re.findall(r"(\d{1,2}[:：]\d{1,2})", raw)
    if len(matches) < 2:
        start_raw, end_raw = raw.replace("：", ":").split("-", 1)
    else:
        start_raw, end_raw = matches[0], matches[1]

    start = _parse_hhmm_to_minutes(start_raw)
    end = _parse_hhmm_to_minutes(end_raw)
    if end <= start:
        end += 24 * 60
    return start, end


def _overlap_minutes(a: Tuple[int, int], b: Tuple[int, int]) -> int:
    left = max(a[0], b[0])
    right = min(a[1], b[1])
    return max(0, right - left)


def _time_match_score(shop: Dict, slots: ParsedSlots, slot_ranges: Dict[str, Tuple[int, int]]) -> float:
    if not slots.time or slots.time not in slot_ranges or not shop.get("open_hours"):
        return 0.0

    try:
        shop_range = _parse_open_hours(shop["open_hours"])
    except (ValueError, TypeError):
        return 0.0

    query_range = slot_ranges[slots.time]
    query_length = query_range[1] - query_range[0]
    overlap = _overlap_minutes(shop_range, query_range)
    if overlap == 0:
        return 0.0

    return min(1.0, overlap / query_length)


def _scene_match_score(shop: Dict, slots: ParsedSlots, scene_aliases: Dict[str, List[str]]) -> float:
    if not slots.scene:
        return 0.0

    aliases = scene_aliases.get(slots.scene, [slots.scene])
    scenes_text = shop.get("scenes", "")
    if any(alias in scenes_text for alias in aliases):
        return 1.0
    return 0.0


def _budget_fit_score(shop: Dict, slots: ParsedSlots) -> float:
    if slots.budget_max is None:
        return 0.0

    avg_price = int(shop["avg_price"])
    budget = max(1, slots.budget_max)

    if avg_price > budget:
        over = avg_price - budget
        return max(0.0, 1.0 - over / budget)

    # In-budget candidates: closer to budget gets a little higher utility.
    return max(0.0, min(1.0, avg_price / budget))


def _score_shop(
    shop: Dict,
    slots: ParsedSlots,
    config: Dict,
    slot_ranges: Dict[str, Tuple[int, int]],
) -> Tuple[float, Dict[str, float]]:
    weights = config["weights"]
    score = float(weights["base_score"])

    components: Dict[str, float] = {
        "budget": _budget_fit_score(shop, slots),
        "location": 1.0 if slots.location and slots.location in shop.get("campus", "") else 0.0,
        "taste": 1.0 if slots.taste and slots.taste in shop.get("tastes", "") else 0.0,
        "scene": _scene_match_score(shop, slots, config["scene_aliases"]),
        "time": _time_match_score(shop, slots, slot_ranges),
    }

    score += float(weights["budget"]) * components["budget"]
    score += float(weights["location"]) * components["location"]
    score += float(weights["taste"]) * components["taste"]
    score += float(weights["scene"]) * components["scene"]
    score += float(weights["time"]) * components["time"]

    if slots.budget_max is not None:
        avg_price = int(shop["avg_price"])
        budget = max(1, slots.budget_max)
        closeness = 1.0 - abs(budget - avg_price) / budget
        components["budget_bonus"] = max(0.0, closeness)
        score += float(weights["budget_bonus"]) * components["budget_bonus"]
    else:
        components["budget_bonus"] = 0.0

    components["matched_fields"] = float(
        sum(1 for key in ["budget", "location", "taste", "scene", "time"] if components[key] > 0)
    )

    return round(min(score, 0.99), 4), components


def _build_reason(shop: Dict, slots: ParsedSlots, components: Dict[str, float], time_match_min: float) -> str:
    parts = []

    if slots.budget_max is not None and int(shop["avg_price"]) <= slots.budget_max:
        parts.append("预算内")
    if slots.location and slots.location in shop.get("campus", ""):
        parts.append(f"位于{slots.location}")
    if slots.taste and slots.taste in shop.get("tastes", ""):
        parts.append(f"口味匹配{slots.taste}")
    if components.get("scene", 0) > 0 and slots.scene:
        parts.append(f"适合{slots.scene}")
    if components.get("time", 0) >= time_match_min and slots.time:
        parts.append(f"{slots.time}时段营业匹配")

    if not parts:
        parts.append("综合评分较高")

    return "，".join(parts) + "。"


def recommend(slots: ParsedSlots, top_k: int = 3) -> List[ShopResult]:
    config = load_scoring_config()
    slot_ranges = _normalize_time_slot_ranges(config)
    time_match_min = float(config["reason_thresholds"]["time_match_min"])
    shops = fetch_active_shops()

    ranked = []
    for shop in shops:
        score, components = _score_shop(shop, slots, config, slot_ranges)
        ranked.append((score, int(components["matched_fields"]), int(shop["avg_price"]), shop, components))

    # Stable tie-break:
    # 1) higher score
    # 2) more matched fields
    # 3) closer to user's budget
    # 4) lower price
    # 5) stable by shop id
    if slots.budget_max is not None:
        ranked.sort(
            key=lambda x: (
                -x[0],
                -x[1],
                abs(x[2] - slots.budget_max),
                x[2],
                x[3]["id"],
            )
        )
    else:
        ranked.sort(key=lambda x: (-x[0], -x[1], x[2], x[3]["id"]))

    results: List[ShopResult] = []
    for score, _, _, shop, components in ranked[:top_k]:
        results.append(
            ShopResult(
                shop_id=shop["id"],
                name=shop["name"],
                campus=shop["campus"],
                avg_price=int(shop["avg_price"]),
                tags=shop["tags"].split("|"),
                score=score,
                reason=_build_reason(shop, slots, components, time_match_min),
            )
        )

    return results
