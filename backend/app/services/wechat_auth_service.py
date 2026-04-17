from __future__ import annotations

import hashlib
import os
from typing import Any, Dict, Optional

import httpx

from app.services.auth_token_service import issue_access_token


def _user_id_from_openid(openid: str) -> str:
    salt = os.getenv("WECHAT_USER_ID_SALT", "chedian-wx-user-v1")
    digest = hashlib.sha256(f"{salt}:{openid}".encode("utf-8")).hexdigest()[:24]
    return f"wx_{digest}"


def _normalize_anonymous_id(value: Optional[str]) -> Optional[str]:
    text = str(value or "").strip()
    return text or None


def login_with_wechat_code(*, code: str, anonymous_id: Optional[str] = None) -> Dict[str, Any]:
    appid = os.getenv("WECHAT_MINIPROGRAM_APPID", "").strip()
    secret = os.getenv("WECHAT_MINIPROGRAM_SECRET", "").strip()
    if not appid or not secret:
        return {
            "ok": False,
            "error": "微信登录未配置，请设置 WECHAT_MINIPROGRAM_APPID / WECHAT_MINIPROGRAM_SECRET。",
            "anonymousId": _normalize_anonymous_id(anonymous_id),
        }

    timeout_seconds = float(os.getenv("WECHAT_AUTH_TIMEOUT_SECONDS", "8"))
    endpoint = "https://api.weixin.qq.com/sns/jscode2session"
    params = {
        "appid": appid,
        "secret": secret,
        "js_code": code.strip(),
        "grant_type": "authorization_code",
    }

    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            resp = client.get(endpoint, params=params)
    except httpx.RequestError as exc:
        return {
            "ok": False,
            "error": f"微信登录请求失败：{exc}",
            "anonymousId": _normalize_anonymous_id(anonymous_id),
        }

    if resp.status_code != 200:
        return {
            "ok": False,
            "error": f"微信登录 HTTP 错误：{resp.status_code}",
            "anonymousId": _normalize_anonymous_id(anonymous_id),
        }

    try:
        data = resp.json()
    except ValueError:
        return {
            "ok": False,
            "error": "微信登录响应解析失败。",
            "anonymousId": _normalize_anonymous_id(anonymous_id),
        }

    openid = str(data.get("openid") or "").strip()
    errcode = data.get("errcode")
    if not openid:
        errmsg = str(data.get("errmsg") or "unknown")
        return {
            "ok": False,
            "error": f"微信登录失败：{errmsg} (errcode={errcode})",
            "anonymousId": _normalize_anonymous_id(anonymous_id),
        }

    user_id = _user_id_from_openid(openid)
    return {
        "ok": True,
        "provider": "wechat_miniprogram",
        "userId": user_id,
        "anonymousId": _normalize_anonymous_id(anonymous_id),
        "message": "微信登录成功",
        **issue_access_token(user_id=user_id),
    }
