from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_wechat_login_proxy_success(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.proxy_routes.login_with_wechat_code",
        lambda **kwargs: {
            "ok": True,
            "provider": "wechat_miniprogram",
            "userId": "wx_test_user",
            "anonymousId": kwargs.get("anonymous_id"),
            "message": "微信登录成功",
        },
    )

    resp = client.post(
        "/api/auth/wechat-login",
        json={"code": "mock-code-1", "anonymousId": "anon_abc"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["provider"] == "wechat_miniprogram"
    assert body["userId"] == "wx_test_user"
    assert body["anonymousId"] == "anon_abc"


def test_wechat_login_proxy_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.proxy_routes.login_with_wechat_code",
        lambda **kwargs: {
            "ok": False,
            "provider": "wechat_miniprogram",
            "error": "微信登录失败：invalid code",
            "anonymousId": kwargs.get("anonymous_id"),
        },
    )

    resp = client.post(
        "/api/auth/wechat-login",
        json={"code": "bad-code"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert "微信登录失败" in body["error"]
