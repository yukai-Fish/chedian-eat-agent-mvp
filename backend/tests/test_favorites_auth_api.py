import sqlite3

from fastapi.testclient import TestClient

from app.main import app
from app.services.auth_token_service import issue_access_token
from app.services.shop_repository import DB_PATH, ensure_database


client = TestClient(app)


def _auth_headers(user_id: str) -> dict:
    token = issue_access_token(user_id=user_id)["accessToken"]
    return {"Authorization": f"Bearer {token}"}


def _cleanup(user_id: str) -> None:
    ensure_database()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM user_favorites WHERE user_id = ?", (user_id,))
        conn.commit()


def test_favorites_requires_authorization_header() -> None:
    resp = client.get("/api/v1/favorites", params={"user_id": "wx_fav_auth_001"})
    assert resp.status_code == 401


def test_favorites_crud_with_valid_token() -> None:
    user_id = "wx_fav_auth_002"
    _cleanup(user_id)
    headers = _auth_headers(user_id)

    create_resp = client.post(
        "/api/v1/favorites",
        json={
            "userId": user_id,
            "shopId": "test-shop-001",
            "shopName": "测试店铺",
            "source": "test-suite",
        },
        headers=headers,
    )
    assert create_resp.status_code == 200
    assert create_resp.json()["ok"] is True

    list_resp = client.get("/api/v1/favorites", params={"user_id": user_id}, headers=headers)
    assert list_resp.status_code == 200
    items = list_resp.json().get("items") or []
    assert any(str(item.get("shop_id") or "").strip() == "test-shop-001" for item in items)

    remove_resp = client.request(
        "DELETE",
        "/api/v1/favorites",
        json={"userId": user_id, "shopId": "test-shop-001"},
        headers=headers,
    )
    assert remove_resp.status_code == 200
    assert remove_resp.json()["ok"] is True

    _cleanup(user_id)

