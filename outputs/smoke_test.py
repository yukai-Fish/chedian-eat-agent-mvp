import os

import requests


def main() -> None:
    base_api = os.getenv("SMOKE_API_BASE", "http://127.0.0.1:8000")
    base_web = os.getenv("SMOKE_WEB_BASE", "http://127.0.0.1:3000")

    checks: list[tuple[str, int, str]] = []

    resp = requests.get(f"{base_api}/api/v1/health", timeout=20)
    checks.append(("health", resp.status_code, resp.text[:200]))

    resp = requests.get(f"{base_api}/api/v1/rankings/today", timeout=20)
    checks.append(("rankings", resp.status_code, resp.text[:300]))

    payload = {
        "query": "清水河附近，预算25，一个人，想吃清淡一点",
        "uid": "codex-smoke",
        "history": [],
    }
    resp = requests.post(f"{base_api}/api/recommend", json=payload, timeout=60)
    checks.append(("recommend_proxy", resp.status_code, resp.text[:600]))

    resp = requests.get(base_web, timeout=20)
    checks.append(("frontend_home", resp.status_code, resp.text[:400]))

    for name, code, snippet in checks:
        print(f"=== {name} | status={code} ===")
        print(snippet)
        print()


if __name__ == "__main__":
    main()
