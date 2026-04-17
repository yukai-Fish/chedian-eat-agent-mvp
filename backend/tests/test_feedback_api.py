from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_dining_feedback_rejects_closed_store(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.proxy_routes.fetch_store_detail_by_name",
        lambda _name: {"businessStatus": {"code": "closed"}},
    )

    saved = {"called": False}

    def _save(_record):
        saved["called"] = True
        return 1

    monkeypatch.setattr("app.api.proxy_routes.save_feedback", _save)

    resp = client.post(
        "/api/feedback",
        json={
            "feedbackType": "dining_feedback",
            "storeName": "川渝牛肉火锅",
            "rating": 5,
            "comment": "味道很好",
        },
    )
    assert resp.status_code == 400
    assert "closed" in str(resp.json().get("detail", "")).lower()
    assert saved["called"] is False


def test_dining_feedback_allows_open_store(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.proxy_routes.fetch_store_detail_by_name",
        lambda _name: {"businessStatus": {"code": "open"}},
    )
    monkeypatch.setattr("app.api.proxy_routes.save_feedback", lambda _record: 123)

    resp = client.post(
        "/api/feedback",
        json={
            "feedbackType": "dining_feedback",
            "storeName": "川渝牛肉火锅",
            "rating": 5,
            "comment": "味道很好",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["id"] == 123

