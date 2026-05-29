"""
Hermes 多用户 JWT 桥：backend 在调用 Hermes 前登记 session_key → user_token，
MCP 工具通过 hermes_session_key 参数（由 Hermes 按 system 上下文传入）解析 JWT。
"""

from __future__ import annotations

import threading
import time
from typing import Optional

_lock = threading.Lock()
_store: dict[str, tuple[str, float]] = {}


def register(session_key: str, user_token: str, *, ttl_seconds: int = 3600) -> str:
    """登记 token，返回规范化后的 session_key。"""
    key = normalize_session_key(session_key)
    token = (user_token or "").strip()
    if not key or not token:
        raise ValueError("session_key and user_token required")
    expires = time.time() + max(1, int(ttl_seconds))
    with _lock:
        _store[key] = (token, expires)
    return key


def resolve(session_key: str | None) -> Optional[str]:
    key = normalize_session_key(session_key or "")
    if not key:
        return None
    now = time.time()
    with _lock:
        entry = _store.get(key)
        if not entry:
            return None
        token, expires = entry
        if now >= expires:
            _store.pop(key, None)
            return None
        return token


def clear(session_key: str | None) -> None:
    key = normalize_session_key(session_key or "")
    if not key:
        return
    with _lock:
        _store.pop(key, None)


def normalize_session_key(session_key: str) -> str:
    s = (session_key or "").strip()
    if not s:
        return ""
    if s.startswith("orientg-"):
        return s
    return f"orientg-{s}"


def reset_for_tests() -> None:
    with _lock:
        _store.clear()
