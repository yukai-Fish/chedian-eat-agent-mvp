from __future__ import annotations

import re
from typing import Dict, List


_CATEGORY_RULES: Dict[str, List[str]] = {
    "hotpot": [
        "火锅",
        "小火锅",
        "四川火锅",
        "串串香",
        "串串",
        "冒菜",
        "麻辣烫",
        "麻辣香锅",
        "牛油锅",
        "鸳鸯锅",
        "肥牛锅",
        "寿喜锅",
    ],
    "barbecue": [
        "烧烤",
        "烤肉",
        "烤串",
        "烧鸟",
        "烤鱼",
        "铁板烧",
        "韩式烤肉",
    ],
    "noodle": [
        "面",
        "拉面",
        "拌面",
        "牛肉面",
        "担担面",
        "粉",
        "米线",
        "螺蛳粉",
        "酸辣粉",
        "刀削面",
        "油泼面",
    ],
    "rice": [
        "盖饭",
        "炒饭",
        "焖饭",
        "煲仔饭",
        "卤肉饭",
        "石锅拌饭",
        "简餐",
    ],
    "drink_dessert": [
        "奶茶",
        "茶饮",
        "果茶",
        "奶盖",
        "咖啡",
        "甜品",
        "冰粉",
        "蛋糕",
    ],
}

_NEGATION_PREFIX = r"(不想|不要|别|不吃|忌口|不太想)"
_LOOSE_QUERY_HINT = re.compile(r"(随便|都行|不限|无所谓)")
_CATEGORY_INTENT_HINT = re.compile(r"(想吃|吃点|来点|推荐|找|要吃|就吃|want|eat)", re.IGNORECASE)
_NON_STRICT_CONTEXT_HINT = re.compile(r"(预算|附近|校区|一个人|聚餐|夜宵|清淡|便宜|营业中)")


def _compact_text(text: str) -> str:
    value = str(text or "").strip().lower()
    if not value:
        return ""
    return re.sub(r"[\s,，。！？!?:：;；()（）【】\[\]_/\\\-]+", "", value)


def _looks_like_category_only_query(raw: str, category_keywords: List[str]) -> bool:
    compact = _compact_text(raw)
    if not compact or len(compact) > 14:
        return False
    if _NON_STRICT_CONTEXT_HINT.search(raw):
        return False

    remaining = compact
    for keyword in category_keywords:
        key_compact = _compact_text(keyword)
        if key_compact:
            remaining = remaining.replace(key_compact, "")

    # Ignore short negation constraints like "不吃牛肉/忌口香菜".
    remaining = re.sub(r"(不吃|不要|忌口|别吃)[\u4e00-\u9fff]{1,6}", "", remaining)
    remaining = re.sub(r"(想吃|吃|来点|找|推荐|我要|来个|就吃|要吃|求推荐)", "", remaining)
    return len(remaining) <= 2


def _is_negated(query_compact: str, keyword_compact: str) -> bool:
    if not query_compact or not keyword_compact:
        return False
    pattern = rf"{_NEGATION_PREFIX}.{{0,3}}{re.escape(keyword_compact)}"
    return re.search(pattern, query_compact) is not None


def extract_query_intents(query: str) -> Dict[str, object]:
    raw = str(query or "").strip()
    compact = _compact_text(raw)
    if not compact:
        return {
            "category_keys": [],
            "category_keywords": [],
            "strict_category": False,
        }

    category_keys: List[str] = []
    category_keywords: List[str] = []
    seen_keyword: set[str] = set()

    for category, keywords in _CATEGORY_RULES.items():
        matched_this_category = False
        for keyword in keywords:
            key_compact = _compact_text(keyword)
            if not key_compact:
                continue
            if key_compact not in compact:
                continue
            if _is_negated(compact, key_compact):
                continue
            if key_compact not in seen_keyword:
                seen_keyword.add(key_compact)
                category_keywords.append(keyword)
            matched_this_category = True
        if matched_this_category:
            category_keys.append(category)

    strict_category = bool(category_keys)
    if strict_category and _LOOSE_QUERY_HINT.search(raw):
        strict_category = False
    if strict_category and not _CATEGORY_INTENT_HINT.search(raw):
        strict_category = _looks_like_category_only_query(raw, category_keywords)

    return {
        "category_keys": category_keys,
        "category_keywords": category_keywords,
        "strict_category": strict_category,
    }


def build_query_with_intent_hint(query: str, intents: Dict[str, object] | None) -> str:
    base = str(query or "").strip()
    if not base:
        return base

    payload = intents if isinstance(intents, dict) else {}
    category_keywords = [str(item).strip() for item in (payload.get("category_keywords") or []) if str(item).strip()]
    if not category_keywords:
        return base

    keywords_text = "、".join(category_keywords[:6])
    strict_category = bool(payload.get("strict_category"))
    if strict_category:
        hint = (
            f"。硬性要求：优先推荐与“{keywords_text}”高度相关的店铺，"
            "弱相关候选仅在候选不足时补充。"
        )
    else:
        hint = f"。优先参考关键词：{keywords_text}。"
    return f"{base}{hint}"
