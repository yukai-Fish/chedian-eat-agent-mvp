import json
from pathlib import Path

from dotenv import load_dotenv
from fastapi.testclient import TestClient


def main() -> None:
    backend_dir = Path(__file__).resolve().parents[1] / "backend"
    load_dotenv(backend_dir / ".env")

    import sys

    sys.path.insert(0, str(backend_dir))

    from app.main import app  # noqa: WPS433
    from app.services.parser import parse_query  # noqa: WPS433
    from app.services.xfyun_workflow_service import ask_workflow  # noqa: WPS433

    query = "预算30，清水河，晚上和同学想吃辣的"

    print("=== parse_query ===")
    print(json.dumps(parse_query(query).model_dump(), ensure_ascii=False, indent=2))

    client = TestClient(app)

    print("\n=== /api/v1/recommend ===")
    resp = client.post("/api/v1/recommend", json={"query": query, "top_k": 3})
    print(json.dumps(resp.json(), ensure_ascii=False, indent=2))

    print("\n=== ask_workflow ===")
    workflow = ask_workflow(query=query, uid="codex-diagnose", chat_id=None, history=[])
    print(json.dumps(workflow, ensure_ascii=False, indent=2)[:4000])

    print("\n=== /api/recommend ===")
    resp = client.post("/api/recommend", json={"query": query, "uid": "codex-diagnose", "history": []})
    print(json.dumps(resp.json(), ensure_ascii=False, indent=2)[:4000])


if __name__ == "__main__":
    main()
