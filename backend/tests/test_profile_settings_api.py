import sqlite3

from fastapi.testclient import TestClient

from app.main import app
from app.services.auth_token_service import issue_access_token
from app.services.shop_repository import DB_PATH, ensure_database


client = TestClient(app)


def _auth_headers(user_id: str) -> dict:
    token = issue_access_token(user_id=user_id)["accessToken"]
    return {"Authorization": f"Bearer {token}"}


def _cleanup_user_profile_settings(user_id: str) -> None:
    ensure_database()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM user_preference_profiles WHERE user_id = ?", (user_id,))
        conn.commit()


def test_profile_settings_requires_user_id() -> None:
    resp = client.get("/api/profile/settings")
    assert resp.status_code == 400


def test_profile_settings_upsert_and_partial_update() -> None:
    user_id = "wx_profile_settings_001"
    _cleanup_user_profile_settings(user_id)

    create_resp = client.post(
        "/api/profile/settings",
        json={
            "userId": user_id,
            "anonymousId": "anon_profile_settings_001",
            "campus": "清水河",
            "tasteTags": ["清淡", "夜宵"],
            "dislikes": ["香菜"],
            "budgetPreference": "20-35元",
            "source": "test-suite",
        },
        headers=_auth_headers(user_id),
    )
    assert create_resp.status_code == 200
    create_body = create_resp.json()
    assert create_body["ok"] is True
    assert create_body["profile"]["campus"] == "清水河"
    assert create_body["profile"]["tasteTags"] == ["清淡", "夜宵"]
    assert create_body["profile"]["dislikes"] == ["香菜"]
    assert create_body["profile"]["budgetPreference"] == "20-35元"

    fetch_resp = client.get("/api/profile/settings", params={"user_id": user_id}, headers=_auth_headers(user_id))
    assert fetch_resp.status_code == 200
    fetch_body = fetch_resp.json()
    assert fetch_body["ok"] is True
    assert fetch_body["profile"]["campus"] == "清水河"
    assert fetch_body["profile"]["tasteTags"] == ["清淡", "夜宵"]
    assert fetch_body["profile"]["dislikes"] == ["香菜"]
    assert fetch_body["profile"]["budgetPreference"] == "20-35元"

    partial_resp = client.post(
        "/api/profile/settings",
        json={
            "userId": user_id,
            "tasteTags": ["想吃辣"],
        },
        headers=_auth_headers(user_id),
    )
    assert partial_resp.status_code == 200
    partial_body = partial_resp.json()
    assert partial_body["ok"] is True
    assert partial_body["profile"]["campus"] == "清水河"
    assert partial_body["profile"]["tasteTags"] == ["想吃辣"]
    assert partial_body["profile"]["dislikes"] == ["香菜"]
    assert partial_body["profile"]["budgetPreference"] == "20-35元"

    _cleanup_user_profile_settings(user_id)
