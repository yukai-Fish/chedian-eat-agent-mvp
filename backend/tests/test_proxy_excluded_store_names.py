import json

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_proxy_passes_excluded_names_to_spark_local(monkeypatch) -> None:
    monkeypatch.setenv("RECOMMEND_PROVIDER", "spark_local")
    captured: dict = {}

    def fake_spark(**kwargs):
        captured.update(kwargs)
        return {"ok": True, "answer": "{}", "finishReason": "stop", "raw": {"source": "spark-local"}}

    monkeypatch.setattr("app.api.proxy_routes.ask_spark_local_recommend", fake_spark)

    resp = client.post(
        "/api/recommend",
        json={
            "query": "清水河，预算25",
            "uid": "u-1",
            "excludeStoreNames": ["韩式拌饭屋", " ", "北方面馆"],
            "history": [],
        },
    )

    assert resp.status_code == 200
    assert captured["exclude_store_names"] == ["韩式拌饭屋", "北方面馆"]


def test_proxy_writes_excluded_names_into_workflow_parameters(monkeypatch) -> None:
    monkeypatch.setenv("RECOMMEND_PROVIDER", "workflow")
    captured: dict = {}

    def fake_workflow(**kwargs):
        captured.update(kwargs)
        return {"ok": True, "answer": "{}", "finishReason": "stop", "raw": {"source": "workflow"}}

    monkeypatch.setattr("app.api.proxy_routes.ask_workflow", fake_workflow)

    resp = client.post(
        "/api/recommend",
        json={
            "query": "清水河，预算25",
            "uid": "u-1",
            "excludeStoreNames": ["韩式拌饭屋", "北方面馆"],
            "history": [],
        },
    )

    assert resp.status_code == 200
    assert "AGENT_EXCLUDED_STORE_NAMES" in captured["parameters"]
    assert json.loads(captured["parameters"]["AGENT_EXCLUDED_STORE_NAMES"]) == ["韩式拌饭屋", "北方面馆"]
