"""Tests for JWT authentication and RBAC."""

import time

import jwt as pyjwt
import pytest

from nss.auth import Role, create_token, verify_token

_TEST_SECRET = "test-secret-key-for-testing"


def test_create_and_verify_round_trip() -> None:
    token = create_token("user-1", "admin", _TEST_SECRET)
    payload = verify_token(token, _TEST_SECRET)
    assert payload["sub"] == "user-1"
    assert payload["role"] == "admin"


def test_expired_token_rejected() -> None:
    token = create_token("user-1", "admin", _TEST_SECRET, expiry_minutes=-1)
    with pytest.raises(pyjwt.ExpiredSignatureError):
        verify_token(token, _TEST_SECRET)


def test_invalid_secret_rejected() -> None:
    token = create_token("user-1", "admin", _TEST_SECRET)
    with pytest.raises(pyjwt.InvalidSignatureError):
        verify_token(token, "wrong-secret")


def test_role_in_payload() -> None:
    for role in Role:
        token = create_token("user-1", role.value, _TEST_SECRET)
        payload = verify_token(token, _TEST_SECRET)
        assert payload["role"] == role.value


def test_token_contains_timestamps() -> None:
    before = int(time.time())
    token = create_token("user-1", "admin", _TEST_SECRET, expiry_minutes=15)
    payload = verify_token(token, _TEST_SECRET)
    assert payload["iat"] >= before
    assert payload["exp"] > payload["iat"]
    assert payload["exp"] - payload["iat"] == 15 * 60


def test_invalid_token_string() -> None:
    with pytest.raises(pyjwt.InvalidTokenError):
        verify_token("not-a-valid-jwt", _TEST_SECRET)
