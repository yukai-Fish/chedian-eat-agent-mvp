from app.services.auth_token_service import AuthTokenError, issue_access_token, verify_access_token


def test_issue_and_verify_access_token_roundtrip() -> None:
    payload = issue_access_token(user_id="wx_auth_roundtrip_001", ttl_seconds=1800)
    token = payload["accessToken"]
    claims = verify_access_token(token)
    assert claims["sub"] == "wx_auth_roundtrip_001"
    assert int(claims["exp"]) > int(claims["iat"])


def test_verify_access_token_rejects_tampered_token() -> None:
    payload = issue_access_token(user_id="wx_auth_roundtrip_002", ttl_seconds=1800)
    token = payload["accessToken"]
    tampered = token[:-1] + ("a" if token[-1] != "a" else "b")
    try:
        verify_access_token(tampered)
    except AuthTokenError:
        return
    raise AssertionError("tampered token should be rejected")

