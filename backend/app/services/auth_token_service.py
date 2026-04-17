from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict


class AuthTokenError(ValueError):
    """Raised when an access token is missing, malformed, or invalid."""


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def _b64url_decode(text: str) -> bytes:
    value = str(text or "").strip()
    if not value:
        raise AuthTokenError("empty token segment")
    padding = "=" * ((4 - len(value) % 4) % 4)
    try:
        return base64.urlsafe_b64decode(value + padding)
    except Exception as exc:  # noqa: BLE001
        raise AuthTokenError("invalid base64 token segment") from exc


def _token_secret() -> str:
    secret = os.getenv("AUTH_TOKEN_SECRET", "").strip()
    if secret:
        return secret
    fallback = os.getenv("WECHAT_MINIPROGRAM_SECRET", "").strip()
    if fallback:
        return fallback
    return "dev-only-change-me"


def _token_ttl_seconds() -> int:
    raw = os.getenv("WECHAT_AUTH_TOKEN_TTL_SECONDS", "604800").strip()
    try:
        value = int(raw)
    except ValueError:
        value = 604800
    return max(300, min(value, 2592000))


def extract_bearer_token(authorization: str | None) -> str:
    value = str(authorization or "").strip()
    if not value:
        raise AuthTokenError("missing Authorization header")
    parts = value.split(" ", 1)
    if len(parts) != 2 or parts[0].strip().lower() != "bearer":
        raise AuthTokenError("Authorization must use Bearer token")
    token = parts[1].strip()
    if not token:
        raise AuthTokenError("missing bearer token")
    return token


def issue_access_token(*, user_id: str, ttl_seconds: int | None = None) -> Dict[str, Any]:
    subject = str(user_id or "").strip()
    if not subject:
        raise AuthTokenError("user_id is required")

    ttl = int(ttl_seconds if ttl_seconds is not None else _token_ttl_seconds())
    now = int(time.time())
    exp = now + max(60, ttl)

    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "iss": "chedian-eat-agent",
        "aud": "miniprogram",
        "ver": 1,
        "sub": subject,
        "iat": now,
        "exp": exp,
    }
    header_seg = _b64url_encode(json.dumps(header, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    payload_seg = _b64url_encode(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    signing_input = f"{header_seg}.{payload_seg}".encode("utf-8")
    signature = hmac.new(_token_secret().encode("utf-8"), signing_input, hashlib.sha256).digest()
    token = f"{header_seg}.{payload_seg}.{_b64url_encode(signature)}"
    return {
        "accessToken": token,
        "tokenType": "Bearer",
        "expiresIn": ttl,
        "expiresAt": datetime.fromtimestamp(exp, tz=timezone.utc).isoformat(),
    }


def verify_access_token(token: str) -> Dict[str, Any]:
    text = str(token or "").strip()
    if not text:
        raise AuthTokenError("empty token")
    parts = text.split(".")
    if len(parts) != 3:
        raise AuthTokenError("token format is invalid")

    header_seg, payload_seg, signature_seg = parts
    signing_input = f"{header_seg}.{payload_seg}".encode("utf-8")
    expected_sig = hmac.new(_token_secret().encode("utf-8"), signing_input, hashlib.sha256).digest()
    actual_sig = _b64url_decode(signature_seg)
    if not hmac.compare_digest(expected_sig, actual_sig):
        raise AuthTokenError("token signature mismatch")

    try:
        header = json.loads(_b64url_decode(header_seg).decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise AuthTokenError("token header is invalid") from exc
    if str((header or {}).get("alg") or "").upper() != "HS256":
        raise AuthTokenError("unsupported token algorithm")

    try:
        payload = json.loads(_b64url_decode(payload_seg).decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise AuthTokenError("token payload is invalid") from exc
    if not isinstance(payload, dict):
        raise AuthTokenError("token payload must be an object")

    sub = str(payload.get("sub") or "").strip()
    if not sub:
        raise AuthTokenError("token subject is missing")

    now = int(time.time())
    try:
        exp = int(payload.get("exp"))
    except (TypeError, ValueError) as exc:
        raise AuthTokenError("token exp is invalid") from exc
    if exp <= now:
        raise AuthTokenError("token expired")

    return payload

