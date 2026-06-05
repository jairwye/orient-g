"""
Hermes 会话上下文：与 hermes_token_bridge 共用 session_key，登记 KB 写权限与 scope。

MCP 写操作（upload/import/assign）据此校验 allow_kb_write 与 folder 归属。
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional

_lock = threading.Lock()
_store: dict[str, tuple["HermesSessionContext", float]] = {}


@dataclass
class HermesSessionContext:
    allow_kb_write: bool = False
    kb_scope: dict[str, list[str]] = field(default_factory=dict)
    orientg_route: str | None = None


def register(
    session_key: str,
    *,
    allow_kb_write: bool = False,
    kb_scope: dict[str, Any] | None = None,
    orientg_route: str | None = None,
    ttl_seconds: int = 3600,
) -> str:
    from backend.services.hermes_token_bridge import normalize_session_key

    key = normalize_session_key(session_key)
    if not key:
        raise ValueError("session_key required")
    scope_raw = kb_scope or {}
    ctx = HermesSessionContext(
        allow_kb_write=bool(allow_kb_write),
        kb_scope={
            "selected_folder_ids": [
                str(x).strip()
                for x in (scope_raw.get("selected_folder_ids") or [])
                if str(x).strip()
            ],
            "selected_collection_ids": [
                str(x).strip()
                for x in (scope_raw.get("selected_collection_ids") or [])
                if str(x).strip()
            ],
            "selected_table_ids": [
                str(x).strip()
                for x in (scope_raw.get("selected_table_ids") or [])
                if str(x).strip()
            ],
        },
        orientg_route=(orientg_route or "").strip() or None,
    )
    expires = time.time() + max(1, int(ttl_seconds))
    with _lock:
        _store[key] = (ctx, expires)
    return key


def resolve(session_key: str | None) -> Optional[HermesSessionContext]:
    from backend.services.hermes_token_bridge import normalize_session_key

    key = normalize_session_key(session_key or "")
    if not key:
        return None
    now = time.time()
    with _lock:
        entry = _store.get(key)
        if not entry:
            return None
        ctx, expires = entry
        if now >= expires:
            _store.pop(key, None)
            return None
        return ctx


def clear(session_key: str | None) -> None:
    from backend.services.hermes_token_bridge import normalize_session_key

    key = normalize_session_key(session_key or "")
    if not key:
        return
    with _lock:
        _store.pop(key, None)


def reset_for_tests() -> None:
    with _lock:
        _store.clear()
