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
                "name": "清水河店A",
                "campus": "清水河",
                "area": "西门",
                "avg_price": 20,
                "open_hours": "10:00-22:00",
                "tastes": "清淡",
                "scenes": "一个人",
                "tags": "面馆",
            },
            {
                "id": "b",
                "name": "沙河店B",
                "campus": "沙河",
                "area": "校内",
                "avg_price": 20,
                "open_hours": "10:00-22:00",
                "tastes": "清淡",
                "scenes": "一个人",
                "tags": "面馆",
            },
        ],
    )

    ranked = _candidate_shops(
        "随便吃点",
        limit=2,
        nearby_context={
            "preferNearby": True,
            "latitude": 30.6742,
            "longitude": 104.1003,
            "campus": "沙河",
            "areaHint": "校内",
        },
    )
    assert len(ranked) == 2
    assert ranked[0]["name"] == "沙河店B"


def test_candidate_shops_prefer_nearby_distance(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.spark_local_recommend_service.parse_query",
        lambda _q: ParsedSlots(budget_max=None, location=None, scene=None, taste=None, time=None),
    )
    monkeypatch.setattr(
        "app.services.spark_local_recommend_service.fetch_active_shops",
        lambda: [
            {
                "id": "west",
                "name": "清水河西门店",
                "campus": "清水河",
                "area": "西门",
                "avg_price": 22,
                "open_hours": "10:00-22:00",
                "tastes": "清淡",
                "scenes": "一个人",
                "tags": "面馆",
            },
            {
                "id": "south",
                "name": "清水河南门店",
                "campus": "清水河",
                "area": "南门",
                "avg_price": 22,
                "open_hours": "10:00-22:00",
                "tastes": "清淡",
                "scenes": "一个人",
                "tags": "面馆",
            },
        ],
    )

    ranked = _candidate_shops(
        "随便吃点",
        limit=2,
        nearby_context={
            "preferNearby": True,
            "latitude": 30.7522,
            "longitude": 103.9259,
            "campus": "清水河",
            "areaHint": "西门",
        },
    )
    assert len(ranked) == 2
    assert ranked[0]["name"] == "清水河西门店"
