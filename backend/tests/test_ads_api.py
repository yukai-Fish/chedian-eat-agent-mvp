from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_ads_public_slots_returns_items() -> None:
    resp = client.get("/api/v1/ads/slots")
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert isinstance(body["items"], list)
    assert "contactWechat" in body


def test_ads_admin_requires_token_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("ADS_ADMIN_TOKEN", "token-123")

    denied = client.get("/api/v1/ads/admin/slots")
    assert denied.status_code == 401

    ok = client.get("/api/v1/ads/admin/slots", headers={"x-admin-token": "token-123"})
    assert ok.status_code == 200
    assert "items" in ok.json()


def test_ads_upsert_toggle_and_click_stats(monkeypatch) -> None:
    monkeypatch.setenv("ADS_ADMIN_TOKEN", "token-456")
    headers = {"x-admin-token": "token-456"}

    upsert = client.post(
        "/api/v1/ads/admin/slots",
        headers=headers,
        json={
            "contactWechat": "bd_test_02",
            "slots": [
                {
                    "id": "test-ad-slot-01",
                    "title": "测试运营广告位",
                    "subtitle": "用于自动化测试",
                    "scene": "测试场景",
                    "audience": "测试用户",
                    "priceLabel": "¥1 / 天",
                    "imageUrl": "/assets/tabbar/ginkgo-gold.png",
                    "landingType": "copy_wechat",
                    "landingValue": "bd_test_02",
                    "rank": 1,
                    "isActive": True,
                    "startsAt": "",
                    "endsAt": "",
                }
            ],
        },
    )
    assert upsert.status_code == 200
    assert upsert.json()["contactWechat"] == "bd_test_02"

    public_before = client.get("/api/v1/ads/slots").json()
    ids_before = {item["id"] for item in public_before["items"]}
    assert "test-ad-slot-01" in ids_before

    click = client.post(
        "/api/v1/events/ad-click",
        json={
            "slotId": "test-ad-slot-01",
            "uid": "u-test",
            "anonymousId": "anon-test",
            "source": "pytest",
        },
    )
    assert click.status_code == 200

    admin_after_click = client.get("/api/v1/ads/admin/slots", headers=headers).json()
    target = next(item for item in admin_after_click["items"] if item["id"] == "test-ad-slot-01")
    assert target["totalClicks"] >= 1

    toggle = client.post(
        "/api/v1/ads/admin/toggle",
        headers=headers,
        json={"slotId": "test-ad-slot-01", "isActive": False},
    )
    assert toggle.status_code == 200

    public_after = client.get("/api/v1/ads/slots").json()
    ids_after = {item["id"] for item in public_after["items"]}
    assert "test-ad-slot-01" not in ids_after
