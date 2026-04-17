from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_store_detail_with_valid_name_returns_structure() -> None:
    resp = client.get("/api/v1/stores/detail", params={"name": "北方面馆"})
    assert resp.status_code == 200
    data = resp.json()
    assert "found" in data
    if data["found"]:
        assert data["store"]["name"]
        assert "avgPrice" in data["store"]
        assert "avgPriceMin" in data["store"]
        assert "avgPriceMax" in data["store"]
        assert "openHours" in data["store"]
        assert "businessStatus" in data["store"]
        assert "imageUrls" in data["store"]
        assert "reviews" in data["store"]


def test_store_detail_without_name_returns_400() -> None:
    resp = client.get("/api/v1/stores/detail")
    assert resp.status_code == 400


def test_store_detail_fuzzy_name_can_match() -> None:
    # "北方面" should still map to seeded "北方面馆".
    resp = client.get("/api/v1/stores/detail", params={"name": "北方面"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["found"] is True
    assert data["store"]["name"] == "北方面馆"
