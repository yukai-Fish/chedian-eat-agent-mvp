from fastapi.testclient import TestClient

from app.main import app
from app.models.schemas import ParsedSlots
from app.services.query_intent_service import build_query_with_intent_hint, extract_query_intents
from app.services.spark_local_recommend_service import _candidate_shops, _sanitize_or_fallback_structured_answer


client = TestClient(app)


def _empty_slots(_q: str) -> ParsedSlots:
    return ParsedSlots(budget_max=None, location=None, scene=None, taste=None, time=None)


def test_candidate_shops_prefers_profile_campus_when_query_missing_location(monkeypatch) -> None:
    monkeypatch.setattr("app.services.spark_local_recommend_service.parse_query", _empty_slots)
    monkeypatch.setattr(
        "app.services.spark_local_recommend_service.fetch_active_shops",
        lambda: [
            {
                "id": "a",
                "name": "qsh-shop",
                "campus": "清水河",
                "area": "校内",
                "avg_price": 26,
                "open_hours": "10:00-22:00",
                "tastes": "清淡",
                "scenes": "一个人",
                "tags": "简餐",
            },
            {
                "id": "b",
                "name": "shahe-shop",
                "campus": "沙河",
                "area": "校内",
                "avg_price": 26,
                "open_hours": "10:00-22:00",
                "tastes": "清淡",
                "scenes": "一个人",
                "tags": "简餐",
            },
        ],
    )

    ranked = _candidate_shops(
        "随便推荐",
        limit=2,
        preference_profile={"campus": "清水河", "tasteTags": [], "dislikes": [], "budgetPreference": ""},
    )
    assert len(ranked) == 2
    assert ranked[0]["name"] == "qsh-shop"


def test_candidate_shops_prefers_profile_budget_when_query_missing_budget(monkeypatch) -> None:
    monkeypatch.setattr("app.services.spark_local_recommend_service.parse_query", _empty_slots)
    monkeypatch.setattr(
        "app.services.spark_local_recommend_service.fetch_active_shops",
        lambda: [
            {
                "id": "cheap",
                "name": "cheap-shop",
                "campus": "清水河",
                "area": "校内",
                "avg_price": 22,
                "open_hours": "10:00-22:00",
                "tastes": "清淡",
                "scenes": "一个人",
                "tags": "简餐",
            },
            {
                "id": "expensive",
                "name": "expensive-shop",
                "campus": "清水河",
                "area": "校内",
                "avg_price": 46,
                "open_hours": "10:00-22:00",
                "tastes": "清淡",
                "scenes": "一个人",
                "tags": "简餐",
            },
        ],
    )

    ranked = _candidate_shops(
        "随便推荐",
        limit=2,
        preference_profile={"campus": "", "tasteTags": [], "dislikes": [], "budgetPreference": "20-35元"},
    )
    assert len(ranked) == 2
    assert ranked[0]["name"] == "cheap-shop"


def test_candidate_shops_filters_profile_dislikes(monkeypatch) -> None:
    monkeypatch.setattr("app.services.spark_local_recommend_service.parse_query", _empty_slots)
    monkeypatch.setattr(
        "app.services.spark_local_recommend_service.fetch_active_shops",
        lambda: [
            {
                "id": "coriander",
                "name": "香菜牛肉面",
                "campus": "清水河",
                "area": "校内",
                "avg_price": 24,
                "open_hours": "10:00-22:00",
                "tastes": "清淡",
                "scenes": "一个人",
                "tags": "面",
            },
            {
                "id": "plain",
                "name": "番茄鸡蛋面",
                "campus": "清水河",
                "area": "校内",
                "avg_price": 24,
                "open_hours": "10:00-22:00",
                "tastes": "清淡",
                "scenes": "一个人",
                "tags": "面",
            },
        ],
    )

    ranked = _candidate_shops(
        "随便推荐",
        limit=5,
        preference_profile={"campus": "", "tasteTags": [], "dislikes": ["香菜"], "budgetPreference": ""},
    )
    names = [item["name"] for item in ranked]
    assert "香菜牛肉面" not in names
    assert "番茄鸡蛋面" in names


def test_candidate_shops_prefers_profile_taste_tags(monkeypatch) -> None:
    monkeypatch.setattr("app.services.spark_local_recommend_service.parse_query", _empty_slots)
    monkeypatch.setattr(
        "app.services.spark_local_recommend_service.fetch_active_shops",
        lambda: [
            {
                "id": "spicy",
                "name": "川味小馆",
                "campus": "清水河",
                "area": "南门",
                "avg_price": 28,
                "open_hours": "10:00-23:00",
                "tastes": "麻辣",
                "scenes": "同学聚餐",
                "tags": "川菜",
            },
            {
                "id": "light",
                "name": "白粥小铺",
                "campus": "清水河",
                "area": "校内",
                "avg_price": 28,
                "open_hours": "10:00-23:00",
                "tastes": "清淡",
                "scenes": "一个人",
                "tags": "粥",
            },
        ],
    )

    ranked = _candidate_shops(
        "随便推荐",
        limit=2,
        preference_profile={"campus": "", "tasteTags": ["想吃辣"], "dislikes": [], "budgetPreference": ""},
    )
    assert len(ranked) == 2
    assert ranked[0]["name"] == "川味小馆"


def test_proxy_recommend_passes_preference_profile_to_spark(monkeypatch) -> None:
    monkeypatch.setenv("RECOMMEND_PROVIDER", "spark_local")

    captured = {}

    def _fake_spark(**kwargs):
        captured.update(kwargs)
        return {
            "ok": True,
            "answer": '{"summary":"ok","batch_size":3,"total_count":0,"recommendations":[]}',
            "finishReason": "stop",
            "raw": {"source": "spark-local"},
        }

    monkeypatch.setattr("app.api.proxy_routes.build_iterative_profile", lambda **_kwargs: {"hasProfile": False})
    monkeypatch.setattr(
        "app.api.proxy_routes.get_profile_settings",
        lambda **_kwargs: {
            "campus": "清水河",
            "taste_tags": ["想吃辣"],
            "dislikes": ["香菜"],
            "budget_preference": "20-35元",
            "updated_at": "2026-04-17 12:00:00",
        },
    )
    monkeypatch.setattr("app.api.proxy_routes.ask_spark_local_recommend", _fake_spark)

    resp = client.post(
        "/api/recommend",
        json={
            "query": "推荐午饭",
            "uid": "u-pref",
            "anonymousId": "anon-pref",
            "userId": "wx-pref-user",
            "history": [],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert isinstance(captured.get("preference_profile"), dict)
    assert captured["preference_profile"].get("campus") == "清水河"
    assert captured["preference_profile"].get("budgetPreference") == "20-35元"


def test_extract_query_intents_treats_category_only_query_as_strict() -> None:
    intents = extract_query_intents("火锅")
    assert intents["strict_category"] is True
    assert "hotpot" in intents["category_keys"]
    assert "火锅" in intents["category_keywords"]


def test_extract_query_intents_respects_negation() -> None:
    intents = extract_query_intents("不想吃火锅，想吃面")
    assert "hotpot" not in intents["category_keys"]
    assert "noodle" in intents["category_keys"]
    assert "面" in intents["category_keywords"]


def test_extract_query_intents_keeps_strict_with_short_negative_constraint() -> None:
    intents = extract_query_intents("火锅 不吃牛肉")
    assert intents["strict_category"] is True
    assert "hotpot" in intents["category_keys"]


def test_candidate_shops_strict_category_filters_unrelated(monkeypatch) -> None:
    monkeypatch.setattr("app.services.spark_local_recommend_service.parse_query", _empty_slots)
    monkeypatch.setattr(
        "app.services.spark_local_recommend_service.fetch_active_shops",
        lambda: [
            {
                "id": "hotpot-1",
                "name": "川渝牛肉火锅",
                "campus": "清水河",
                "area": "校内",
                "avg_price": 35,
                "open_hours": "10:00-22:00",
                "tastes": "麻辣",
                "scenes": "聚餐",
                "tags": "火锅,川菜",
            },
            {
                "id": "noodle-1",
                "name": "兰州拉面",
                "campus": "清水河",
                "area": "校内",
                "avg_price": 18,
                "open_hours": "10:00-22:00",
                "tastes": "清淡",
                "scenes": "一个人",
                "tags": "面",
            },
            {
                "id": "rice-1",
                "name": "黄焖鸡米饭",
                "campus": "清水河",
                "area": "校内",
                "avg_price": 20,
                "open_hours": "10:00-22:00",
                "tastes": "家常",
                "scenes": "一个人",
                "tags": "盖饭",
            },
        ],
    )

    ranked = _candidate_shops(
        "想吃火锅",
        limit=5,
        preference_profile={"campus": "", "tasteTags": [], "dislikes": [], "budgetPreference": ""},
    )
    names = [item["name"] for item in ranked]

    assert "川渝牛肉火锅" in names
    assert "兰州拉面" not in names
    assert "黄焖鸡米饭" not in names


def test_proxy_recommend_sends_intent_enhanced_query_to_spark(monkeypatch) -> None:
    monkeypatch.setenv("RECOMMEND_PROVIDER", "spark_local")
    captured = {}

    def _fake_spark(**kwargs):
        captured.update(kwargs)
        return {
            "ok": True,
            "answer": '{"summary":"ok","batch_size":3,"total_count":0,"recommendations":[]}',
            "finishReason": "stop",
            "raw": {"source": "spark-local"},
        }

    monkeypatch.setattr("app.api.proxy_routes.build_iterative_profile", lambda **_kwargs: {"hasProfile": False})
    monkeypatch.setattr("app.api.proxy_routes.ask_spark_local_recommend", _fake_spark)

    resp = client.post(
        "/api/recommend",
        json={
            "query": "想吃火锅",
            "uid": "u-intent",
            "anonymousId": "anon-intent",
            "history": [],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert isinstance(captured.get("query"), str)
    assert captured["query"].startswith("想吃火锅")
    assert "硬性要求" in captured["query"]


def test_build_query_with_intent_hint_for_non_strict_query() -> None:
    intents = extract_query_intents("随便来点奶茶都行")
    enhanced = build_query_with_intent_hint("随便来点奶茶都行", intents)
    assert "优先参考关键词" in enhanced


def test_candidate_shops_strict_category_returns_empty_when_no_related(monkeypatch) -> None:
    monkeypatch.setattr("app.services.spark_local_recommend_service.parse_query", _empty_slots)
    monkeypatch.setattr(
        "app.services.spark_local_recommend_service.fetch_active_shops",
        lambda: [
            {
                "id": "noodle-1",
                "name": "兰州拉面",
                "campus": "清水河",
                "area": "校内",
                "avg_price": 18,
                "open_hours": "10:00-22:00",
                "tastes": "清淡",
                "scenes": "一个人",
                "tags": "面",
            },
            {
                "id": "rice-1",
                "name": "黄焖鸡米饭",
                "campus": "清水河",
                "area": "校内",
                "avg_price": 22,
                "open_hours": "10:00-22:00",
                "tastes": "家常",
                "scenes": "一个人",
                "tags": "盖饭",
            },
        ],
    )
    ranked = _candidate_shops(
        "火锅",
        limit=5,
        preference_profile={"campus": "", "tasteTags": [], "dislikes": [], "budgetPreference": ""},
    )
    assert ranked == []


def test_sanitize_or_fallback_answer_filters_unknown_names() -> None:
    candidates = [
        {
            "name": "川渝牛肉火锅",
            "avg_price": 35,
            "scenes": "聚餐",
            "_rankScore": 2.8,
            "_categoryMatched": True,
            "_categoryHits": 2,
            "_queryTermHits": 2,
        },
        {
            "name": "清汤火锅馆",
            "avg_price": 32,
            "scenes": "朋友小聚",
            "_rankScore": 2.3,
            "_categoryMatched": True,
            "_categoryHits": 1,
            "_queryTermHits": 1,
        },
    ]
    answer = (
        '{"summary":"测试","batch_size":3,"total_count":2,"recommendations":['
        '{"name":"某某网红店","score":99,"reason":"r1","recommend_dish":"d1","scene_fit":"s1","warning":""},'
        '{"name":"川渝牛肉火锅","score":92,"reason":"r2","recommend_dish":"d2","scene_fit":"s2","warning":""}'
        "]}"
    )
    sanitized_text, meta = _sanitize_or_fallback_structured_answer(
        answer=answer,
        query="想吃火锅",
        candidates=candidates,
        query_intents={"strict_category": True, "category_keywords": ["火锅"]},
    )
    assert meta["mode"] == "sanitize-json"
    assert meta["dropped_count"] >= 1
    assert "某某网红店" not in sanitized_text
    assert "川渝牛肉火锅" in sanitized_text
    assert "清汤火锅馆" in sanitized_text


def test_sanitize_or_fallback_answer_falls_back_on_non_json() -> None:
    candidates = [
        {
            "name": "川渝牛肉火锅",
            "avg_price": 35,
            "scenes": "聚餐",
            "_rankScore": 2.8,
            "_categoryMatched": True,
            "_categoryHits": 2,
            "_queryTermHits": 2,
        }
    ]
    sanitized_text, meta = _sanitize_or_fallback_structured_answer(
        answer="这是一段自由文本，不是JSON",
        query="想吃火锅",
        candidates=candidates,
        query_intents={"strict_category": True, "category_keywords": ["火锅"]},
    )
    assert meta["mode"] == "fallback-non-json"
    assert "川渝牛肉火锅" in sanitized_text
