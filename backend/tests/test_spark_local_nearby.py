from app.models.schemas import ParsedSlots
from app.services.spark_local_recommend_service import _candidate_shops


def test_candidate_shops_prefer_nearby_campus(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.spark_local_recommend_service.parse_query",
        lambda _q: ParsedSlots(budget_max=None, location=None, scene=None, taste=None, time=None),
    )
    monkeypatch.setattr(
        "app.services.spark_local_recommend_service.fetch_active_shops",
        lambda: [
            {
                "id": "a",
                "name": "campus-a-shop",
                "campus": "campus-a",
                "area": "west",
                "avg_price": 20,
                "open_hours": "10:00-22:00",
                "tastes": "light",
                "scenes": "solo",
                "tags": "noodle",
            },
            {
                "id": "b",
                "name": "campus-b-shop",
                "campus": "campus-b",
                "area": "inner",
                "avg_price": 20,
                "open_hours": "10:00-22:00",
                "tastes": "light",
                "scenes": "solo",
                "tags": "noodle",
            },
        ],
    )

    ranked = _candidate_shops(
        "anything",
        limit=2,
        nearby_context={
            "preferNearby": True,
            "latitude": 30.6742,
            "longitude": 104.1003,
            "campus": "campus-b",
            "areaHint": "inner",
        },
    )
    assert len(ranked) == 2
    assert ranked[0]["name"] == "campus-b-shop"


def test_candidate_shops_prefer_nearby_distance(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.spark_local_recommend_service.parse_query",
        lambda _q: ParsedSlots(budget_max=None, location=None, scene=None, taste=None, time=None),
    )
    monkeypatch.setattr(
        "app.services.spark_local_recommend_service.fetch_active_shops",
        lambda: [
            {
                "id": "near",
                "name": "near-shop",
                "campus": "campus-a",
                "area": "west",
                "latitude": 30.7522,
                "longitude": 103.9349,
                "avg_price": 22,
                "open_hours": "10:00-22:00",
                "tastes": "light",
                "scenes": "solo",
                "tags": "noodle",
            },
            {
                "id": "far",
                "name": "far-shop",
                "campus": "campus-a",
                "area": "south",
                "latitude": 30.6742,
                "longitude": 104.1003,
                "avg_price": 22,
                "open_hours": "10:00-22:00",
                "tastes": "light",
                "scenes": "solo",
                "tags": "noodle",
            },
        ],
    )

    ranked = _candidate_shops(
        "anything",
        limit=2,
        nearby_context={
            "preferNearby": True,
            "latitude": 30.7522,
            "longitude": 103.9349,
            "campus": "campus-a",
            "areaHint": "west",
        },
    )
    assert len(ranked) == 2
    assert ranked[0]["name"] == "near-shop"


def test_candidate_shops_prefers_real_coordinates_when_present(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.spark_local_recommend_service.parse_query",
        lambda _q: ParsedSlots(budget_max=None, location=None, scene=None, taste=None, time=None),
    )
    monkeypatch.setattr(
        "app.services.spark_local_recommend_service.fetch_active_shops",
        lambda: [
            {
                "id": "latlng-near",
                "name": "latlng-near-shop",
                "campus": "unknown-campus",
                "area": "unknown-area",
                "latitude": 30.7521,
                "longitude": 103.9348,
                "avg_price": 22,
                "open_hours": "10:00-22:00",
                "tastes": "light",
                "scenes": "solo",
                "tags": "noodle",
            },
            {
                "id": "latlng-far",
                "name": "latlng-far-shop",
                "campus": "unknown-campus",
                "area": "unknown-area",
                "latitude": 30.6742,
                "longitude": 104.1003,
                "avg_price": 22,
                "open_hours": "10:00-22:00",
                "tastes": "light",
                "scenes": "solo",
                "tags": "noodle",
            },
        ],
    )

    ranked = _candidate_shops(
        "anything",
        limit=2,
        nearby_context={
            "preferNearby": True,
            "latitude": 30.7522,
            "longitude": 103.9349,
            "campus": "unknown-campus",
            "areaHint": "unknown-area",
        },
    )
    assert len(ranked) == 2
    assert ranked[0]["name"] == "latlng-near-shop"
    assert ranked[0]["distance_km"] is not None


def test_candidate_shops_prefer_walking_time_when_available(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.spark_local_recommend_service.parse_query",
        lambda _q: ParsedSlots(budget_max=None, location=None, scene=None, taste=None, time=None),
    )
    monkeypatch.setattr(
        "app.services.spark_local_recommend_service.fetch_active_shops",
        lambda: [
            {
                "id": "near",
                "name": "near-shop",
                "campus": "campus-a",
                "area": "west",
                "latitude": 30.7522,
                "longitude": 103.9349,
                "avg_price": 22,
                "open_hours": "10:00-22:00",
                "tastes": "light",
                "scenes": "solo",
                "tags": "noodle",
            },
            {
                "id": "fast-walk",
                "name": "fast-walk-shop",
                "campus": "campus-a",
                "area": "west",
                "latitude": 30.7528,
                "longitude": 103.9400,
                "avg_price": 22,
                "open_hours": "10:00-22:00",
                "tastes": "light",
                "scenes": "solo",
                "tags": "noodle",
            },
        ],
    )
    monkeypatch.setattr(
        "app.services.spark_local_recommend_service._tencent_map_api_key",
        lambda: "test-key",
    )
    monkeypatch.setattr(
        "app.services.spark_local_recommend_service._fetch_walking_metrics",
        lambda _olat, _olng, dlat, _dlng: (900, 1200) if abs(dlat - 30.7522) < 1e-6 else (600, 480),
    )

    ranked = _candidate_shops(
        "anything",
        limit=2,
        nearby_context={
            "preferNearby": True,
            "latitude": 30.7522,
            "longitude": 103.9349,
            "campus": "campus-a",
            "areaHint": "west",
        },
    )
    assert len(ranked) == 2
    assert ranked[0]["name"] == "fast-walk-shop"
    assert ranked[0]["walking_minutes"] is not None
    assert ranked[0]["walking_distance_m"] is not None


def test_candidate_shops_fallback_when_walking_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.spark_local_recommend_service.parse_query",
        lambda _q: ParsedSlots(budget_max=None, location=None, scene=None, taste=None, time=None),
    )
    monkeypatch.setattr(
        "app.services.spark_local_recommend_service.fetch_active_shops",
        lambda: [
            {
                "id": "near",
                "name": "near-shop",
                "campus": "campus-a",
                "area": "west",
                "latitude": 30.7522,
                "longitude": 103.9349,
                "avg_price": 22,
                "open_hours": "10:00-22:00",
                "tastes": "light",
                "scenes": "solo",
                "tags": "noodle",
            },
            {
                "id": "far",
                "name": "far-shop",
                "campus": "campus-a",
                "area": "west",
                "latitude": 30.6742,
                "longitude": 104.1003,
                "avg_price": 22,
                "open_hours": "10:00-22:00",
                "tastes": "light",
                "scenes": "solo",
                "tags": "noodle",
            },
        ],
    )
    monkeypatch.setattr(
        "app.services.spark_local_recommend_service._tencent_map_api_key",
        lambda: "test-key",
    )
    monkeypatch.setattr(
        "app.services.spark_local_recommend_service._fetch_walking_metrics",
        lambda *_args, **_kwargs: None,
    )

    ranked = _candidate_shops(
        "anything",
        limit=2,
        nearby_context={
            "preferNearby": True,
            "latitude": 30.7522,
            "longitude": 103.9349,
            "campus": "campus-a",
            "areaHint": "west",
        },
    )
    assert len(ranked) == 2
    assert ranked[0]["name"] == "near-shop"
    assert ranked[0]["walking_minutes"] is None
