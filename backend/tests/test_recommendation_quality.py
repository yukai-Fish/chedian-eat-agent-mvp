from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_case_spicy_group_dinner_qingshuihe() -> None:
    payload = {"query": "预算30，清水河，晚上和同学想吃辣的", "top_k": 3}
    resp = client.post("/api/v1/recommend", json=payload)
    data = resp.json()

    assert resp.status_code == 200
    assert data["parsed"]["location"] == "清水河"
    assert data["parsed"]["taste"] == "辣"
    assert data["parsed"]["scene"] == "同学聚餐"
    assert data["parsed"]["time"] == "晚餐"
    assert data["recommendations"][0]["name"] in {"川味小馆", "韩式拌饭屋"}


def test_case_light_solo_lunch_shahe() -> None:
    payload = {"query": "20以内，沙河，中午一个人，清淡点", "top_k": 3}
    resp = client.post("/api/v1/recommend", json=payload)
    data = resp.json()

    assert resp.status_code == 200
    assert data["parsed"]["location"] == "沙河"
    assert data["parsed"]["scene"] == "一个人"
    assert data["parsed"]["taste"] == "清淡"
    assert data["parsed"]["time"] == "午餐"
    assert data["recommendations"][0]["name"] == "番茄牛腩粉"


def test_case_night_snack_qingshuihe() -> None:
    payload = {"query": "夜宵想吃辣，清水河，预算40，和朋友一起", "top_k": 3}
    resp = client.post("/api/v1/recommend", json=payload)
    data = resp.json()
    names = [item["name"] for item in data["recommendations"]]

    assert resp.status_code == 200
    assert data["parsed"]["time"] == "夜宵"
    assert data["parsed"]["location"] == "清水河"
    assert data["parsed"]["taste"] == "辣"
    assert data["parsed"]["scene"] == "同学聚餐"
    assert "深夜小串" in names
