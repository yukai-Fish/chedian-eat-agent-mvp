import sqlite3

from fastapi.testclient import TestClient

from app.main import app
from app.services.shop_repository import DB_PATH, ensure_database
from app.services.usage_events import log_query_event


client = TestClient(app)


def _cleanup_user_data(user_id: str, anonymous_id: str) -> None:
    ensure_database()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM user_favorites WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM usage_events WHERE user_id = ? OR anonymous_id = ?", (user_id, anonymous_id))
        conn.commit()


def test_profile_data_requires_user_id() -> None:
    resp = client.get("/api/profile/data")
    assert resp.status_code == 400


def test_profile_sync_local_migrates_favorites_and_history() -> None:
    user_id = "wx_test_sync_user"
    anonymous_id = "anon_profile_sync_001"
    _cleanup_user_data(user_id, anonymous_id)

    log_query_event("anonymous-only-query", uid=anonymous_id, anonymous_id=anonymous_id, source="test")

    resp = client.post(
        "/api/profile/sync-local",
        json={
            "userId": user_id,
            "anonymousId": anonymous_id,
            "favorites": ["custom-favorite-shop"],
            "queryHistory": ["history-a", "history-b"],
            "source": "test-sync",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["migratedFavorites"] >= 1
    assert body["migratedHistory"] >= 1
    assert body["linkedHistoryEvents"] >= 1
    assert "custom-favorite-shop" in body["favorites"]

    data_resp = client.get("/api/profile/data", params={"user_id": user_id})
    assert data_resp.status_code == 200
    data_body = data_resp.json()
    assert data_body["ok"] is True
    assert "custom-favorite-shop" in data_body["favorites"]
    assert "history-a" in data_body["queryHistory"]

    _cleanup_user_data(user_id, anonymous_id)
