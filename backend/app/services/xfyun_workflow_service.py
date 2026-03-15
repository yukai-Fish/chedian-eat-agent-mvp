import json
import os
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx


ERROR_HINTS = {
    20204: "Workflow is unpublished or draft.",
    20207: "Workflow is unpublished or draft.",
    20369: "Service busy, please retry later.",
    20804: "OpenAPI timeout.",
    23900: "Session timeout or chat not found.",
}


def _error_hint_by_code(code: Optional[int]) -> Optional[str]:
    if code is None:
        return None
    if code in ERROR_HINTS:
        return ERROR_HINTS[code]
    if 20900 <= code <= 20903:
        return "Auth/quota issue. Check key/secret/permissions/quota."
    return None


def _build_authorization() -> Tuple[Optional[str], Optional[str]]:
    api_key = os.getenv("XFYUN_API_KEY", "").strip()
    api_secret = os.getenv("XFYUN_API_SECRET", "").strip()
    if not api_key or not api_secret:
        return None, "XFYUN_API_KEY or XFYUN_API_SECRET is missing."
    return f"Bearer {api_key}:{api_secret}", None


def _is_retryable_request_error(exc: httpx.RequestError) -> bool:
    if isinstance(exc, (httpx.ConnectError, httpx.ReadError, httpx.WriteError, httpx.RemoteProtocolError)):
        return True
    message = str(exc).lower()
    markers = (
        "unexpected_eof_while_reading",
        "eof occurred in violation of protocol",
        "connection reset",
        "connection aborted",
        "broken pipe",
        "tls",
        "ssl",
    )
    return any(marker in message for marker in markers)


def validate_and_map_history(history: List[Dict[str, Any]]) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
    if not history:
        return [], None

    if history[0].get("role") != "user":
        return None, "history first role must be user."

    mapped: List[Dict[str, Any]] = []
    expected_role = "user"
    for idx, item in enumerate(history):
        role = item.get("role")
        content = str(item.get("content") or "").strip()
        content_type = str(item.get("content_type") or item.get("contentType") or "text").strip().lower()

        if role not in {"user", "assistant"}:
            return None, f"history[{idx}] role must be user/assistant."
        if role != expected_role:
            return None, f"history[{idx}] role order invalid, expected {expected_role}."
        if not content:
            return None, f"history[{idx}] content is empty."
        if content_type not in {"text", "image"}:
            return None, f"history[{idx}] content_type must be text/image."

        mapped.append(
            {
                "role": role,
                "content_type": content_type,
                "content": content,
            }
        )
        expected_role = "assistant" if expected_role == "user" else "user"

    return mapped, None


def _build_chat_payload(
    query: str,
    uid: Optional[str],
    chat_id: Optional[str],
    mapped_history: List[Dict[str, Any]],
    stream: bool,
    extra_parameters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    merged_parameters: Dict[str, Any] = {}
    if isinstance(extra_parameters, dict):
        merged_parameters.update(extra_parameters)

    # Keep contract key, and also provide common alias for workflows that directly bind `query`.
    merged_parameters["AGENT_USER_INPUT"] = query
    merged_parameters.setdefault("query", query)

    payload: Dict[str, Any] = {
        "flow_id": os.getenv("XFYUN_FLOW_ID", "7436739079683477504"),
        "uid": uid or "demo-user",
        "parameters": merged_parameters,
        "ext": {
            "bot_id": "workflow",
            "caller": "workflow",
        },
        "stream": stream,
    }
    if chat_id:
        payload["chat_id"] = chat_id
    if mapped_history:
        payload["history"] = mapped_history
    return payload


def _extract_sse_json_events(raw_text: str) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    for line in raw_text.splitlines():
        text = line.strip()
        if not text or not text.startswith("data:"):
            continue
        data = text[5:].strip()
        if not data or data == "[DONE]":
            continue
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            events.append(parsed)
    return events


def _merge_stream_events(events: List[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    if not events:
        return None, "stream response does not contain parseable JSON frames."

    merged_content: List[str] = []
    final_finish_reason: Optional[str] = None
    final_event_data: Optional[Any] = None
    final_usage: Optional[Any] = None

    last_code: Optional[int] = None
    last_message: Optional[str] = None
    last_id: Optional[str] = None
    last_created: Optional[Any] = None
    last_workflow_step: Optional[Any] = None
    last_role: str = "assistant"

    for body in events:
        if isinstance(body.get("code"), int):
            last_code = body.get("code")
        if body.get("message") is not None:
            last_message = str(body.get("message"))
        if body.get("id") is not None:
            last_id = str(body.get("id"))
        if body.get("created") is not None:
            last_created = body.get("created")
        if body.get("workflow_step") is not None:
            last_workflow_step = body.get("workflow_step")

        choice = (body.get("choices") or [{}])[0]
        if isinstance(choice, dict):
            delta = choice.get("delta") or {}
            if isinstance(delta, dict):
                role = delta.get("role")
                if isinstance(role, str) and role:
                    last_role = role
                part = delta.get("content")
                if isinstance(part, str) and part:
                    merged_content.append(part)
            finish_reason = choice.get("finish_reason")
            if isinstance(finish_reason, str):
                final_finish_reason = finish_reason

        if body.get("event_data") is not None:
            final_event_data = body.get("event_data")
        if body.get("usage") is not None:
            final_usage = body.get("usage")

    if last_code is None:
        last_code = 0
    if last_message is None:
        last_message = "Success"

    merged_body: Dict[str, Any] = {
        "code": last_code,
        "message": last_message,
        "id": last_id,
        "created": last_created,
        "workflow_step": last_workflow_step,
        "choices": [
            {
                "delta": {
                    "role": last_role,
                    "content": "".join(merged_content),
                },
                "index": 0,
                "finish_reason": final_finish_reason,
            }
        ],
    }
    if final_usage is not None:
        merged_body["usage"] = final_usage
    if final_event_data is not None:
        merged_body["event_data"] = final_event_data

    return merged_body, None


def _parse_workflow_response_body(resp: httpx.Response, stream: bool) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    if not stream:
        try:
            body = resp.json()
        except ValueError:
            return None, "workflow returned non-JSON response."
        if not isinstance(body, dict):
            return None, "workflow response body is not an object."
        return body, None

    events = _extract_sse_json_events(resp.text)
    return _merge_stream_events(events)


def _send_json_request(
    endpoint: str,
    headers: Dict[str, str],
    payload: Dict[str, Any],
    timeout_seconds: float,
    max_retries: int,
) -> Tuple[Optional[httpx.Response], Optional[str], Optional[int], Optional[str]]:
    resp: Optional[httpx.Response] = None
    timeout_error: Optional[str] = None
    request_error: Optional[str] = None

    for attempt in range(max_retries + 1):
        try:
            with httpx.Client(timeout=timeout_seconds, trust_env=False, http2=False) as client:
                resp = client.post(endpoint, headers=headers, json=payload)
            timeout_error = None
            request_error = None
            break
        except httpx.ReadTimeout:
            timeout_error = f"workflow timeout (>{timeout_seconds}s)."
            if attempt < max_retries:
                time.sleep(0.4 * (attempt + 1))
                continue
        except httpx.RequestError as exc:
            request_error = f"workflow request failed: {exc}"
            if attempt < max_retries and _is_retryable_request_error(exc):
                time.sleep(0.4 * (attempt + 1))
                continue
            return None, request_error, None, None

    if resp is None:
        return None, timeout_error or request_error or "workflow request failed.", 20804, None
    return resp, None, None, None


def _finalize_workflow_result(body: Dict[str, Any]) -> Dict[str, Any]:
    code = body.get("code")
    if code != 0:
        message = body.get("message") or "workflow returned business error."
        hint = _error_hint_by_code(code if isinstance(code, int) else None)
        error = f"{message} (code={code})"
        if hint:
            error = f"{error} {hint}"
        return {
            "ok": False,
            "error": error,
            "code": code if isinstance(code, int) else None,
            "raw": body,
        }

    choice = (body.get("choices") or [{}])[0]
    delta = choice.get("delta") or {}
    answer = delta.get("content")
    finish_reason = choice.get("finish_reason")
    event_data = body.get("event_data")

    if finish_reason == "interrupt":
        return {
            "ok": False,
            "error": "workflow interrupted, resume required.",
            "code": 0,
            "finishReason": "interrupt",
            "raw": body,
        }

    if finish_reason not in {None, "stop", "ping"}:
        return {
            "ok": False,
            "error": f"unsupported finish_reason: {finish_reason}",
            "code": 0,
            "finishReason": finish_reason,
            "raw": body,
        }

    if not answer and finish_reason == "stop":
        return {
            "ok": False,
            "error": "workflow response missing choices[0].delta.content.",
            "code": 0,
            "finishReason": finish_reason,
            "raw": body,
        }

    result: Dict[str, Any] = {
        "ok": True,
        "answer": answer,
        "finishReason": finish_reason,
        "raw": body,
    }
    if event_data is not None and finish_reason == "ping":
        result["raw"] = body
    return result


def ask_workflow(
    query: str,
    uid: Optional[str] = None,
    chat_id: Optional[str] = None,
    history: Optional[List[Dict[str, Any]]] = None,
    stream: Optional[bool] = None,
    parameters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    app_id = os.getenv("XFYUN_APP_ID", "").strip()
    if not app_id:
        return {"ok": False, "error": "XFYUN_APP_ID is missing.", "code": None, "raw": None}

    auth_header, auth_err = _build_authorization()
    if auth_err:
        return {"ok": False, "error": auth_err, "code": None, "raw": None}

    mapped_history, history_err = validate_and_map_history(history or [])
    if history_err:
        return {"ok": False, "error": history_err, "code": None, "raw": {"history": history}}

    base_url = os.getenv("XFYUN_BASE_URL", "https://xingchen-api.xf-yun.com").rstrip("/")
    endpoint = f"{base_url}/workflow/v1/chat/completions"
    timeout_seconds = float(os.getenv("XFYUN_TIMEOUT_SECONDS", "45"))
    max_retries = int(os.getenv("XFYUN_MAX_RETRIES", "2"))
    stream_enabled = stream if stream is not None else os.getenv("XFYUN_STREAM", "false").lower() == "true"

    headers = {
        "Authorization": auth_header,
        "Content-Type": "application/json",
    }
    payload = _build_chat_payload(
        query=query,
        uid=uid,
        chat_id=chat_id,
        mapped_history=mapped_history or [],
        stream=stream_enabled,
        extra_parameters=parameters,
    )

    resp, error, code, _ = _send_json_request(endpoint, headers, payload, timeout_seconds, max_retries)
    if resp is None:
        return {"ok": False, "error": error, "code": code, "raw": None}
    if resp.status_code != 200:
        return {
            "ok": False,
            "error": f"workflow HTTP error: {resp.status_code}",
            "code": resp.status_code,
            "raw": resp.text,
        }

    body, parse_err = _parse_workflow_response_body(resp, stream_enabled)
    if parse_err:
        return {
            "ok": False,
            "error": parse_err,
            "code": None,
            "raw": resp.text,
        }
    return _finalize_workflow_result(body or {})


def resume_workflow(
    event_id: str,
    event_type: str,
    content: Optional[str],
    stream: Optional[bool] = None,
) -> Dict[str, Any]:
    app_id = os.getenv("XFYUN_APP_ID", "").strip()
    if not app_id:
        return {"ok": False, "error": "XFYUN_APP_ID is missing.", "code": None, "raw": None}

    auth_header, auth_err = _build_authorization()
    if auth_err:
        return {"ok": False, "error": auth_err, "code": None, "raw": None}

    base_url = os.getenv("XFYUN_BASE_URL", "https://xingchen-api.xf-yun.com").rstrip("/")
    endpoint = f"{base_url}/workflow/v1/resume"
    timeout_seconds = float(os.getenv("XFYUN_TIMEOUT_SECONDS", "45"))
    max_retries = int(os.getenv("XFYUN_MAX_RETRIES", "2"))
    stream_enabled = stream if stream is not None else os.getenv("XFYUN_STREAM", "false").lower() == "true"

    headers = {
        "Authorization": auth_header,
        "Content-Type": "application/json",
    }
    payload: Dict[str, Any] = {
        "event_id": event_id,
        "event_type": event_type,
        "content": content or "",
        "stream": stream_enabled,
    }

    resp, error, code, _ = _send_json_request(endpoint, headers, payload, timeout_seconds, max_retries)
    if resp is None:
        return {"ok": False, "error": error, "code": code, "raw": None}
    if resp.status_code != 200:
        return {
            "ok": False,
            "error": f"workflow resume HTTP error: {resp.status_code}",
            "code": resp.status_code,
            "raw": resp.text,
        }

    body, parse_err = _parse_workflow_response_body(resp, stream_enabled)
    if parse_err:
        return {
            "ok": False,
            "error": parse_err,
            "code": None,
            "raw": resp.text,
        }
    return _finalize_workflow_result(body or {})


def upload_workflow_file(file_name: str, content: bytes, content_type: str = "application/octet-stream") -> Dict[str, Any]:
    app_id = os.getenv("XFYUN_APP_ID", "").strip()
    if not app_id:
        return {"ok": False, "error": "XFYUN_APP_ID is missing.", "code": None, "raw": None}

    auth_header, auth_err = _build_authorization()
    if auth_err:
        return {"ok": False, "error": auth_err, "code": None, "raw": None}

    base_url = os.getenv("XFYUN_BASE_URL", "https://xingchen-api.xf-yun.com").rstrip("/")
    endpoint = f"{base_url}/workflow/v1/upload_file"
    timeout_seconds = float(os.getenv("XFYUN_TIMEOUT_SECONDS", "45"))

    headers = {"Authorization": auth_header}
    try:
        with httpx.Client(timeout=timeout_seconds, trust_env=False, http2=False) as client:
            resp = client.post(
                endpoint,
                headers=headers,
                files={"file": (file_name, content, content_type)},
            )
    except httpx.RequestError as exc:
        return {"ok": False, "error": f"workflow upload failed: {exc}", "code": None, "raw": None}

    if resp.status_code != 200:
        return {
            "ok": False,
            "error": f"workflow upload HTTP error: {resp.status_code}",
            "code": resp.status_code,
            "raw": resp.text,
        }

    try:
        body = resp.json()
    except ValueError:
        return {"ok": False, "error": "workflow upload returned non-JSON response.", "code": None, "raw": resp.text}

    code = body.get("code")
    if code != 0:
        message = body.get("message") or "workflow upload business error."
        hint = _error_hint_by_code(code if isinstance(code, int) else None)
        error = f"{message} (code={code})"
        if hint:
            error = f"{error} {hint}"
        return {"ok": False, "error": error, "code": code if isinstance(code, int) else None, "raw": body}

    data = body.get("data") or {}
    file_url = data.get("url") if isinstance(data, dict) else None
    return {"ok": True, "url": file_url, "raw": body, "code": 0}
