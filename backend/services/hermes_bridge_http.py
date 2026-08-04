"""
Hermes MCP 子进程 → backend 的 HTTP 会话桥。

MCP 由 Hermes 以独立 stdio 子进程启动，无法读取 uvicorn 进程内 hermes_token_bridge。
当本地 bridge 未命中时，经 ORIENTG_INTERNAL_BASE_URL 回调 backend internal API。
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

_CACHE_TTL_S = 3.0
_cache_lock = threading.Lock()
_session_cache: dict[str, tuple["RemoteHermesSession", float]] = {}


@dataclass
class RemoteHermesSession:
    user_token: str
    kb_scope: dict[str, list[str]] = field(default_factory=dict)
    allow_kb_write: bool = False
    orientg_route: str | None = None
    native_mcp_reply: bool = False


def _internal_base_url() -> str:
    from backend.config import settings

    raw = (
        (os.environ.get("ORIENTG_INTERNAL_BASE_URL") or "").strip()
        or (getattr(settings, "orientg_internal_base_url", None) or "").strip()
    )
    if not raw and (settings.app_env or "").strip().lower() in ("", "development", "dev", "local"):
        raw = "http://127.0.0.1:8000"
    return raw.rstrip("/")


def _bridge_secret() -> str:
    from backend.config import settings

    dedicated = (
        (os.environ.get("ORIENTG_MCP_BRIDGE_SECRET") or "").strip()
        or (getattr(settings, "orientg_mcp_bridge_secret", None) or "").strip()
    )
    if dedicated:
        return dedicated
    env = (settings.app_env or "").strip().lower()
    if env in ("production", "prod"):
        return ""
    return (settings.auth_secret or "").strip()


def bridge_http_enabled() -> bool:
    return bool(_internal_base_url())


def _bridge_headers() -> dict[str, str]:
    secret = _bridge_secret()
    if not secret:
        return {}
    return {"X-OrientG-MCP-Bridge-Secret": secret}


def _post_json(path: str, body: dict[str, Any]) -> httpx.Response:
    base = _internal_base_url()
    url = f"{base}{path}"
    with httpx.Client(timeout=10.0) as client:
        return client.post(url, json=body, headers=_bridge_headers())


def _cache_get(key: str) -> RemoteHermesSession | None:
    now = time.time()
    with _cache_lock:
        entry = _session_cache.get(key)
        if not entry:
            return None
        sess, expires = entry
        if now >= expires:
            _session_cache.pop(key, None)
            return None
        return sess


def _cache_put(key: str, sess: RemoteHermesSession) -> None:
    with _cache_lock:
        _session_cache[key] = (sess, time.time() + _CACHE_TTL_S)


def clear_session_cache_for_tests() -> None:
    with _cache_lock:
        _session_cache.clear()


def fetch_remote_session(session_key: str | None) -> RemoteHermesSession | None:
    from backend.services.hermes_token_bridge import normalize_session_key

    key = normalize_session_key(session_key or "")
    if not key or not bridge_http_enabled():
        return None

    cached = _cache_get(key)
    if cached:
        return cached

    try:
        resp = _post_json("/api/internal/hermes/session/resolve", {"hermes_session_key": key})
    except Exception:
        logger.debug("hermes bridge HTTP resolve failed for %s", key, exc_info=True)
        return None

    if resp.status_code == 404:
        return None
    if resp.status_code != 200:
        logger.warning(
            "hermes bridge HTTP resolve unexpected status=%s key=%s",
            resp.status_code,
            key,
        )
        return None

    data = resp.json()
    token = (data.get("user_token") or "").strip()
    if not token:
        return None

    scope_raw = data.get("kb_scope") or {}
    sess = RemoteHermesSession(
        user_token=token,
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
        allow_kb_write=bool(data.get("allow_kb_write")),
        orientg_route=(data.get("orientg_route") or "").strip() or None,
        native_mcp_reply=bool(data.get("native_mcp_reply")),
    )
    _cache_put(key, sess)
    return sess


def consume_remote_kb_ask_budget(session_key: str | None) -> Optional[str]:
    """远程预算扣减。桥启用却不可达时 fail-closed（返回 deny 字符串）。"""
    from backend.services.hermes_token_bridge import normalize_session_key

    key = normalize_session_key(session_key or "")
    if not key or not bridge_http_enabled():
        return None

    try:
        resp = _post_json(
            "/api/internal/hermes/session/kb-ask-budget/consume",
            {"hermes_session_key": key},
        )
    except Exception:
        logger.debug("hermes bridge HTTP budget consume failed for %s", key, exc_info=True)
        return "orientg_kb_ask budget bridge unavailable"

    if resp.status_code != 200:
        return "orientg_kb_ask budget bridge unavailable"
    data = resp.json()
    if data.get("denied"):
        return str(data.get("reason") or "orientg_kb_ask budget denied")
    return None
