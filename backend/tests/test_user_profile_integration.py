from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_recommend_workflow_injects_profile_into_parameters(monkeypatch) -> None:
    monkeypatch.setenv("RECOMMEND_PROVIDER", "workflow")
    captured = {}

    monkeypatch.setattr(
        "app.api.proxy_routes.build_iterative_profile",
        lambda **kwargs: {
            "hasProfile": True,
            "summary": "口味偏好：辣；常见预算：20-35元。",
            "signals": {"topTastes": ["辣"]},
            "stats": {"queryCount": 3, "feedbackCount": 1},
        },
    )

    def _fake_workflow(**kwargs):
        captured.update(kwargs)
        return {"ok": True, "answer": "ok", "finishReason": "stop", "raw": {}}

    monkeypatch.setattr("app.api.proxy_routes.ask_workflow", _fake_workflow)

    resp = client.post(
        "/api/recommend",
        json={"query": "想吃辣", "anonymousId": "anon_1", "history": []},
    )
    assert resp.status_code == 200
    assert "AGENT_USER_PROFILE_SUMMARY" in (captured.get("parameters") or {})
    assert "AGENT_USER_PROFILE_JSON" in (captured.get("parameters") or {})


def test_recommend_spark_injects_profile_into_service(monkeypatch) -> None:
    monkeypatch.setenv("RECOMMEND_PROVIDER", "spark_local")
    captured = {}

    monkeypatch.setattr(
        "app.api.proxy_routes.build_iterative_profile",
        lambda **kwargs: {
            "hasProfile": True,
            "summary": "就餐场景偏好：同学聚餐。",
            "signals": {"topScenes": ["同学聚餐"]},
            "stats": {"queryCount": 4, "feedbackCount": 2},
        },
    )

    def _fake_spark(**kwargs):
        captured.update(kwargs)
        return {"ok": True, "answer": "ok", "finishReason": "stop", "raw": {}}

    monkeypatch.setattr("app.api.proxy_routes.ask_spark_local_recommend", _fake_spark)

    resp = client.post(
        "/api/recommend",
        json={"query": "适合同学聚餐", "anonymousId": "anon_2", "history": []},
    )
    assert resp.status_code == 200
    assert isinstance(captured.get("user_profile"), dict)
    assert captured["user_profile"]["hasProfile"] is True
