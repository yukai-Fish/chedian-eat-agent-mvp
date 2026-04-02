from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_proxy_recommend_passthrough_when_workflow_unstructured(monkeypatch) -> None:
    monkeypatch.setenv("RECOMMEND_PROVIDER", "workflow")
    monkeypatch.setattr(
        "app.api.proxy_routes.ask_workflow",
        lambda **kwargs: {
            "ok": True,
            "answer": "This is an unstructured natural-language response.",
            "finishReason": "stop",
            "raw": {"source": "workflow"},
        },
    )

    resp = client.post(
        "/api/recommend",
        json={
            "query": "清水河附近，预算25，一个人，想吃清淡一点",
            "uid": "test-user",
            "history": [],
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["finishReason"] == "stop"
    assert body["answer"] == "This is an unstructured natural-language response."
    assert body["raw"]["source"] == "workflow"


def test_proxy_recommend_passthrough_when_card_friendly(monkeypatch) -> None:
    monkeypatch.setenv("RECOMMEND_PROVIDER", "workflow")
    workflow_answer = "\n".join(
        [
            "1. 川香阁",
            "店名：川香阁",
            "推荐理由：离你近，口味匹配。",
            "推荐菜：冒菜",
            "适合场景：一个人晚饭",
            "可能不足：高峰期排队。",
        ]
    )
    monkeypatch.setattr(
        "app.api.proxy_routes.ask_workflow",
        lambda **kwargs: {
            "ok": True,
            "answer": workflow_answer,
            "finishReason": "stop",
            "raw": {"source": "workflow"},
        },
    )

    resp = client.post(
        "/api/recommend",
        json={
            "query": "清水河附近，预算25，一个人，想吃清淡一点",
            "uid": "test-user",
            "history": [],
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["finishReason"] == "stop"
    assert body["answer"] == workflow_answer
    assert body["raw"]["source"] == "workflow"


def test_proxy_recommend_passthrough_when_structured_json(monkeypatch) -> None:
    monkeypatch.setenv("RECOMMEND_PROVIDER", "workflow")
    workflow_answer = (
        '{"query":"test","summary":"s","batch_size":3,"total_count":6,'
        '"recommendations":[{"name":"A","score":92,"reason":"r",'
        '"recommend_dish":"d","scene_fit":"晚餐","warning":"w"}]}'
    )
    monkeypatch.setattr(
        "app.api.proxy_routes.ask_workflow",
        lambda **kwargs: {
            "ok": True,
            "answer": workflow_answer,
            "finishReason": "stop",
            "raw": {"source": "workflow"},
        },
    )

    resp = client.post(
        "/api/recommend",
        json={
            "query": "test",
            "uid": "test-user",
            "history": [],
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["finishReason"] == "stop"
    assert body["answer"] == workflow_answer
    assert body["raw"]["source"] == "workflow"
