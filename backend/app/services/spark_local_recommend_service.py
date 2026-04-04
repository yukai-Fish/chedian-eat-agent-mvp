from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.services.parser import parse_query
from app.services.shop_repository import fetch_active_shops


_UNAVAILABLE_ENDPOINTS: set[str] = set()


def _build_auth_header() -> Tuple[Optional[str], Optional[str]]:
    # Preferred for Spark HTTP service.
    api_password = os.getenv("XFYUN_SPARKX_API_PASSWORD", "").strip()
    if not api_password:
        # Final fallback using key:secret convention.
        api_key = os.getenv("XFYUN_API_KEY", "").strip()
        api_secret = os.getenv("XFYUN_API_SECRET", "").strip()
        if api_key and api_secret:
            api_password = f"{api_key}:{api_secret}"

    if not api_password:
        return None, "Missing Spark API password. Set XFYUN_SPARKX_API_PASSWORD."

    return f"Bearer {api_password}", None


def _headers() -> Dict[str, str]:
    auth, _ = _build_auth_header()
    return {
        "Authorization": auth or "",
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json; charset=utf-8",
    }


def _candidate_shops(query: str, limit: int = 30) -> List[Dict[str, Any]]:
    slots = parse_query(query)
    shops = fetch_active_shops()

    campus = (slots.location or "").strip()
    budget = slots.budget_max
    taste = (slots.taste or "").strip()
    scene = (slots.scene or "").strip()
    time_hint = (slots.time or "").strip()

    scored: List[Tuple[float, Dict[str, Any]]] = []
    for item in shops:
        score = 0.0
        if campus and campus in str(item.get("campus", "")):
            score += 3.0

        avg_price = int(item.get("avg_price", 0) or 0)
        if budget is not None:
            if avg_price <= budget:
                score += 2.6
            else:
                score += max(0.0, 1.0 - (avg_price - budget) / max(1, budget))

        if taste and taste in str(item.get("tastes", "")):
            score += 1.6
        if scene and scene in str(item.get("scenes", "")):
            score += 1.3
        if time_hint and time_hint in str(item.get("open_hours", "")):
            score += 0.6

        scored.append((score, item))

    scored.sort(key=lambda x: (-x[0], int(x[1].get("avg_price", 0) or 0), str(x[1].get("id", ""))))
    selected = [row for _, row in scored[:limit]]

    return [
        {
            "id": str(row.get("id", "")),
            "name": str(row.get("name", "")),
            "campus": str(row.get("campus", "")),
            "area": str(row.get("area", "")),
            "avg_price": int(row.get("avg_price", 0) or 0),
            "open_hours": str(row.get("open_hours", "")),
            "tastes": str(row.get("tastes", "")),
            "scenes": str(row.get("scenes", "")),
            "tags": str(row.get("tags", "")),
        }
        for row in selected
    ]


def _messages(query: str, shops: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    system_prompt = """
You are a ranking assistant for a campus food recommendation app.
Return STRICT JSON only (no markdown, no extra text) with this shape:
{
  "query": "<original query>",
  "summary": "<one sentence recommendation strategy in Chinese>",
  "batch_size": 3,
  "total_count": <int>,
  "recommendations": [
    {
      "name": "...",
      "score": 0-100,
      "reason": "...",
      "recommend_dish": "...",
      "scene_fit": "...",
      "warning": "..."
    }
  ]
}
Rules:
1) Use shop names only from provided candidates.
2) Sort by score descending.
3) Output at most 9 recommendations.
4) If a field is unknown, use empty string.
""".strip()

    user_prompt = f"User query: {query}\n\nCandidates(JSON):\n{json.dumps(shops, ensure_ascii=False)}"
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _extract_content(data: Dict[str, Any]) -> str:
    choices = data.get("choices") or []
    if not choices:
        return ""
    first = choices[0] or {}
    message = first.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return content
    if isinstance(message, str):
        return message
    text = first.get("text")
    if isinstance(text, str):
        return text
    delta = first.get("delta") or {}
    if isinstance(delta, dict):
        content = delta.get("content")
        if isinstance(content, str):
            return content
    return ""


def _strip_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    return stripped.strip()


def _endpoints() -> List[str]:
    primary = os.getenv("XFYUN_SPARKX2_ENDPOINT", "https://spark-api-open.xf-yun.com/x2/chat/completions").strip()
    backup = os.getenv("XFYUN_SPARKX15_ENDPOINT", "https://spark-api-open.xf-yun.com/v2/chat/completions").strip()
    values = [primary]
    if backup and backup not in values:
        values.append(backup)
    values = [url for url in values if url and url not in _UNAVAILABLE_ENDPOINTS]
    if not values:
        values = [primary]
    return values


def _is_no_route(resp_text: str) -> bool:
    text = (resp_text or "").lower()
    return "no category route found" in text or "enginecode=10404" in text


def ask_spark_local_recommend(
    *,
    query: str,
    uid: Optional[str] = None,
    timeout_seconds: Optional[float] = None,
) -> Dict[str, Any]:
    auth, auth_err = _build_auth_header()
    if auth_err:
        return {"ok": False, "error": auth_err, "code": None, "raw": {"source": "spark-local"}}

    timeout = timeout_seconds or float(os.getenv("XFYUN_TIMEOUT_SECONDS", "45"))
    temperature = float(os.getenv("XFYUN_SPARKX_TEMPERATURE", "0.3"))
    max_tokens = int(os.getenv("XFYUN_SPARKX_MAX_TOKENS", "1800"))
    model = os.getenv("XFYUN_SPARKX_MODEL", "spark-x").strip() or "spark-x"
    thinking_mode = os.getenv("XFYUN_SPARKX_THINKING", "disabled").strip().lower() or "disabled"
    if thinking_mode not in {"enabled", "disabled", "auto"}:
        thinking_mode = "disabled"

    shops = _candidate_shops(query, limit=30)
    payload = {
        "model": model,
        "messages": _messages(query, shops),
        "stream": False,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "user": uid or "web-user",
        "thinking": {"type": thinking_mode},
    }

    headers = _headers()
    headers["Authorization"] = auth

    attempts: List[Dict[str, Any]] = []
    last_status: Optional[int] = None
    last_text: Optional[str] = None
    chosen_endpoint: Optional[str] = None
    parsed: Optional[Dict[str, Any]] = None

    for endpoint in _endpoints():
        try:
            with httpx.Client(timeout=timeout, trust_env=False, http2=False) as client:
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                resp = client.post(endpoint, headers=headers, content=body)
        except httpx.RequestError as exc:
            attempts.append({"endpoint": endpoint, "ok": False, "request_error": str(exc)})
            continue

        last_status = resp.status_code
        last_text = resp.text
        if resp.status_code != 200:
            attempts.append({"endpoint": endpoint, "ok": False, "status_code": resp.status_code, "response_text": resp.text[:360]})
            if _is_no_route(resp.text):
                _UNAVAILABLE_ENDPOINTS.add(endpoint)
            continue

        try:
            data = resp.json()
        except ValueError:
            attempts.append({"endpoint": endpoint, "ok": False, "status_code": resp.status_code, "response_text": resp.text[:360]})
            continue

        content = _strip_fence(_extract_content(data))
        if not content:
            attempts.append({"endpoint": endpoint, "ok": False, "reason": "missing_content"})
            continue

        parsed = data
        chosen_endpoint = endpoint
        break

    if parsed is None:
        return {
            "ok": False,
            "error": f"Spark HTTP error: {last_status}" if last_status else "Spark request failed.",
            "code": last_status,
            "raw": {
                "source": "spark-local",
                "endpoint": chosen_endpoint,
                "candidate_count": len(shops),
                "attempts": attempts,
                "response_text": last_text,
                "model": model,
            },
        }

    answer = _strip_fence(_extract_content(parsed))
    if not answer:
        return {
            "ok": False,
            "error": "Spark response missing content.",
            "code": None,
            "raw": {
                "source": "spark-local",
                "endpoint": chosen_endpoint,
                "candidate_count": len(shops),
                "attempts": attempts,
                "upstream": parsed,
                "model": model,
            },
        }

    sid = parsed.get("sid") or parsed.get("id")
    return {
        "ok": True,
        "answer": answer,
        "finishReason": "stop",
        "raw": {
            "source": "spark-local",
            "sid": sid,
            "id": parsed.get("id"),
            "endpoint": chosen_endpoint,
            "candidate_count": len(shops),
            "attempts": attempts,
            "usage": parsed.get("usage"),
            "model": model,
            "upstream": parsed,
        },
    }
