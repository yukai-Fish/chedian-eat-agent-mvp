from __future__ import annotations

from fastapi import HTTPException

from app.services.auth_token_service import AuthTokenError, extract_bearer_token, verify_access_token


def require_authenticated_user(*, authorization: str | None, expected_user_id: str | None = None) -> str:
    try:
        token = extract_bearer_token(authorization)
        claims = verify_access_token(token)
    except AuthTokenError as exc:
        raise HTTPException(status_code=401, detail=f"unauthorized: {exc}") from exc

    token_user_id = str((claims or {}).get("sub") or "").strip()
    if not token_user_id:
        raise HTTPException(status_code=401, detail="unauthorized: token subject is missing")
    if expected_user_id and token_user_id != expected_user_id:
        raise HTTPException(status_code=403, detail="forbidden: token user mismatch")
    return token_user_id

