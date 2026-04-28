from app.services.auth_service import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_hash_and_verify():
    raw = "password123"
    hashed = hash_password(raw)

    assert hashed != raw
    assert verify_password(raw, hashed) is True
    assert verify_password("wrong", hashed) is False


def test_create_and_decode_access_token():
    token = create_access_token("user-1", "student")
    payload = decode_access_token(token)

    assert payload["sub"] == "user-1"
    assert payload["role"] == "student"
    assert payload["jti"]
    assert "exp" in payload
