"""Hermes 多用户：session_key → JWT 桥（内存 TTL）。"""

import time

import jwt
import pytest

from backend.config import settings
from backend.services import hermes_token_bridge as bridge


@pytest.fixture(autouse=True)
def _clear_bridge():
    bridge.reset_for_tests()
    yield
    bridge.reset_for_tests()


def _jwt(sub: str = "alice") -> str:
    return jwt.encode(
        {"sub": sub, "iat": int(time.time()), "exp": int(time.time()) + 3600},
        settings.auth_secret,
        algorithm="HS256",
    )


def test_register_and_resolve():
    key = "orientg-test-1"
    tok = _jwt()
    bridge.register(key, tok, ttl_seconds=60)
    assert bridge.resolve(key) == tok


def test_resolve_missing_returns_none():
    assert bridge.resolve("orientg-missing") is None


def test_expired_token_returns_none():
    key = "orientg-exp"
    bridge.register(key, _jwt(), ttl_seconds=1)
    time.sleep(1.05)
    assert bridge.resolve(key) is None
