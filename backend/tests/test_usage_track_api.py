import json
import sqlite3

from fastapi.testclient import TestClient

from app.main import app
from app.services.shop_repository import DB_PATH, ensure_database


client = TestClient(app)


def _cleanup(source: str) -> None:
    ensure_database()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM usage_events WHERE source = ?", (source,))
        conn.commit()


def _latest_event(source: str) -> dict:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT event_type, uid, anonymous_id, user_id, query_text, shop_id, shop_name, source, meta_json
            FROM usage_events
            WHERE source = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (source,),
        ).fetchone()
    return dict(row) if row else {}


def test_track_event_proxy_writes_usage_event() -> None:
    source = "pytest_track_proxy"
    _cleanup(source)

    resp = client.post(
        "/api/events/track",
        json={
            "eventType": "profile_card_click",
            "uid": "u-track-1",
            "anonymousId": "anon-track-1",
            "userId": "wx-track-1",
            "source": source,
            "meta": {
                "entry": "profile_home",
                "isAuthenticated": True,
            },
        },
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    event = _latest_event(source)
    assert event["event_type"] == "profile_card_click"
    assert event["uid"] == "u-track-1"
    assert event["anonymous_id"] == "anon-track-1"
    assert event["user_id"] == "wx-track-1"
    assert event["source"] == source
    assert json.loads(event["meta_json"] or "{}") == {
        "entry": "profile_home",
        "isAuthenticated": True,
    }

    _cleanup(source)


def test_track_event_v1_writes_usage_event() -> None:
    source = "pytest_track_v1"
    _cleanup(source)

    resp = client.post(
        "/api/v1/events/track",
        json={
            "eventType": "recommendation_conversion",
            "queryText": "清水河附近一个人吃",
            "shopId": "store:001",
            "shopName": "测试店铺",
            "source": source,
            "meta": {
                "rank": 1,
                "from": "recommend_card",
            },
        },
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    event = _latest_event(source)
    assert event["event_type"] == "recommendation_conversion"
    assert event["query_text"] == "清水河附近一个人吃"
    assert event["shop_id"] == "store:001"
    assert event["shop_name"] == "测试店铺"
    assert event["source"] == source

    _cleanup(source)
