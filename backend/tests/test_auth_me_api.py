from fastapi.testclient import TestClient

from app.main import app
from app.services.auth_token_service import issue_access_token


client = TestClient(app)


def test_auth_me_requires_token() -> None:
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_auth_me_with_token() -> None:
    token = issue_access_token(user_id="wx_auth_me_001")["accessToken"]
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["userId"] == "wx_auth_me_001"
    assert body["provider"] == "wechat_miniprogram"

