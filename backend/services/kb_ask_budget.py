"""Hermes 会话级 orientg_kb_ask 调用预算（与 hermes_token_bridge 同 session_key）。"""

from __future__ import annotations

import threading
import time
from typing import Optional

_lock = threading.Lock()
# session_key -> (max_calls | None, used, expires)
_store: dict[str, tuple[int | None, int, float]] = {}


def register_session_kb_budget(session_key: str, max_calls: int | None, *, ttl_seconds: int = 3600) -> None:
    from backend.services.hermes_token_bridge import normalize_session_key

    key = normalize_session_key(session_key)
    if not key:
        return
    cap: int | None
    if max_calls is None:
        cap = None
    else:
        cap = max(0, int(max_calls))
    expires = time.time() + max(1, int(ttl_seconds))
    with _lock:
        _store[key] = (cap, 0, expires)


def check_and_consume_ask(session_key: str | None) -> Optional[str]:
    """
    若会话已登记预算且已用尽，返回 deny 原因；否则计数 +1 并返回 None。
    未登记预算的会话不限制（如 CLI 直调 token）。
    """
    from backend.services.hermes_token_bridge import normalize_session_key

    key = normalize_session_key(session_key or "")
    if not key:
        return None
    now = time.time()
    with _lock:
        entry = _store.get(key)
        if not entry:
            return None
        max_calls, used, expires = entry
        if now >= expires:
            _store.pop(key, None)
            return None
        if max_calls is None:
            return None
        if used >= max_calls:
            return f"orientg_kb_ask budget exhausted (max {max_calls} per session)"
        _store[key] = (max_calls, used + 1, expires)
        return None


def clear_session_budget(session_key: str | None) -> None:
    from backend.services.hermes_token_bridge import normalize_session_key

    key = normalize_session_key(session_key or "")
    if not key:
        return
    with _lock:
        _store.pop(key, None)


def reset_for_tests() -> None:
    with _lock:
        _store.clear()
