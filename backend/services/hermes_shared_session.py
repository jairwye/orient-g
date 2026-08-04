"""Hermes 会话 PostgreSQL 共享存储：跨 uvicorn worker / MCP HTTP 桥读取。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import text

from backend.database import engine, init_hermes_session_store_table

logger = logging.getLogger(__name__)

_TOKEN_SEAL_PREFIX = "v1:"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_key(session_key: str) -> str:
    from backend.services.hermes_token_bridge import normalize_session_key

    return normalize_session_key(session_key)


def _token_seal_key() -> bytes:
    from backend.config import settings

    dedicated = (settings.orientg_mcp_bridge_secret or "").strip()
    auth = (settings.auth_secret or "").strip()
    material = (dedicated or auth or "orientg-dev-session-seal").encode("utf-8")
    return hashlib.sha256(b"hermes-session-token-v1:" + material).digest()


def seal_user_token(user_token: str) -> str:
    """JWT at-rest 密封（不可逆密钥派生 + 流密码 + HMAC）。兼容明文旧行。"""
    pt = (user_token or "").strip().encode("utf-8")
    if not pt:
        return ""
    key = _token_seal_key()
    nonce = secrets.token_bytes(16)
    out = bytearray()
    counter = 0
    while len(out) < len(pt):
        block = hashlib.sha256(key + nonce + counter.to_bytes(4, "big")).digest()
        out.extend(block)
        counter += 1
    ct = bytes(a ^ b for a, b in zip(pt, out[: len(pt)]))
    tag = hmac.new(key, nonce + ct, hashlib.sha256).digest()[:16]
    return _TOKEN_SEAL_PREFIX + base64.urlsafe_b64encode(nonce + tag + ct).decode("ascii")


def unseal_user_token(stored: str) -> str:
    raw = (stored or "").strip()
    if not raw:
        return ""
    if not raw.startswith(_TOKEN_SEAL_PREFIX):
        # 兼容升级前明文行
        return raw
    try:
        blob = base64.urlsafe_b64decode(raw[len(_TOKEN_SEAL_PREFIX) :].encode("ascii"))
        nonce, tag, ct = blob[:16], blob[16:32], blob[32:]
        key = _token_seal_key()
        expect = hmac.new(key, nonce + ct, hashlib.sha256).digest()[:16]
        if not hmac.compare_digest(tag, expect):
            logger.warning("hermes session token seal MAC mismatch")
            return ""
        out = bytearray()
        counter = 0
        while len(out) < len(ct):
            block = hashlib.sha256(key + nonce + counter.to_bytes(4, "big")).digest()
            out.extend(block)
            counter += 1
        pt = bytes(a ^ b for a, b in zip(ct, out[: len(ct)]))
        return pt.decode("utf-8")
    except Exception:
        logger.debug("unseal hermes session token failed", exc_info=True)
        return ""


def persist_session(
    session_key: str,
    user_token: str,
    *,
    kb_scope: dict[str, Any] | None = None,
    allow_kb_write: bool = False,
    orientg_route: str | None = None,
    kb_budget_max: int | None = None,
    ttl_seconds: int = 3600,
) -> None:
    init_hermes_session_store_table()
    key = _normalize_key(session_key)
    token = (user_token or "").strip()
    if not key or not token:
        return
    expires = _now() + timedelta(seconds=max(1, int(ttl_seconds)))
    scope = kb_scope or {}
    sealed = seal_user_token(token)
    sql = text(
        """
        INSERT INTO hermes_session_store (
            session_key, user_token, kb_scope_json, allow_kb_write, orientg_route,
            kb_budget_max, kb_budget_used, expires_at
        ) VALUES (
            :k, :t, :scope, :w, :route, :bmax, 0, :exp
        )
        ON CONFLICT (session_key) DO UPDATE SET
            user_token = EXCLUDED.user_token,
            kb_scope_json = EXCLUDED.kb_scope_json,
            allow_kb_write = EXCLUDED.allow_kb_write,
            orientg_route = EXCLUDED.orientg_route,
            kb_budget_max = EXCLUDED.kb_budget_max,
            expires_at = EXCLUDED.expires_at
        """
    )
    try:
        with engine.connect() as conn:
            conn.execute(
                sql,
                {
                    "k": key,
                    "t": sealed,
                    "scope": json.dumps(scope, ensure_ascii=False),
                    "w": bool(allow_kb_write),
                    "route": (orientg_route or "").strip() or None,
                    "bmax": kb_budget_max,
                    "exp": expires,
                },
            )
            conn.commit()
    except Exception:
        logger.debug("persist hermes session failed for %s", key, exc_info=True)


def load_session(session_key: str | None) -> Optional[dict[str, Any]]:
    init_hermes_session_store_table()
    key = _normalize_key(session_key or "")
    if not key:
        return None
    sql = text(
        """
        SELECT user_token, kb_scope_json, allow_kb_write, orientg_route,
               kb_budget_max, kb_budget_used, expires_at
        FROM hermes_session_store
        WHERE session_key = :k
        """
    )
    try:
        with engine.connect() as conn:
            row = conn.execute(sql, {"k": key}).mappings().first()
        if not row:
            return None
        expires = row.get("expires_at")
        if expires is not None:
            exp = expires if expires.tzinfo else expires.replace(tzinfo=timezone.utc)
            if _now() >= exp:
                delete_session(key)
                return None
        scope_raw = row.get("kb_scope_json") or "{}"
        try:
            scope = json.loads(scope_raw) if isinstance(scope_raw, str) else dict(scope_raw or {})
        except Exception:
            scope = {}
        token = unseal_user_token(str(row.get("user_token") or ""))
        if not token:
            return None
        return {
            "user_token": token,
            "kb_scope": scope,
            "allow_kb_write": bool(row.get("allow_kb_write")),
            "orientg_route": (row.get("orientg_route") or "").strip() or None,
            "kb_budget_max": row.get("kb_budget_max"),
            "kb_budget_used": int(row.get("kb_budget_used") or 0),
        }
    except Exception:
        logger.debug("load hermes session failed for %s", key, exc_info=True)
        return None


def delete_session(session_key: str) -> None:
    key = _normalize_key(session_key)
    if not key:
        return
    try:
        with engine.connect() as conn:
            conn.execute(text("DELETE FROM hermes_session_store WHERE session_key = :k"), {"k": key})
            conn.commit()
    except Exception:
        logger.debug("delete hermes session failed for %s", key, exc_info=True)


def consume_kb_budget_db(session_key: str | None) -> Optional[str]:
    """DB 侧预算扣减；返回 deny 原因或 None。"""
    init_hermes_session_store_table()
    key = _normalize_key(session_key or "")
    if not key:
        return None
    sel = text(
        """
        SELECT kb_budget_max, kb_budget_used, expires_at
        FROM hermes_session_store
        WHERE session_key = :k
        FOR UPDATE
        """
    )
    upd = text(
        """
        UPDATE hermes_session_store
        SET kb_budget_used = kb_budget_used + 1
        WHERE session_key = :k
        """
    )
    try:
        with engine.begin() as conn:
            row = conn.execute(sel, {"k": key}).mappings().first()
            if not row:
                return None
            expires = row.get("expires_at")
            if expires is not None:
                exp = expires if expires.tzinfo else expires.replace(tzinfo=timezone.utc)
                if _now() >= exp:
                    return None
            max_calls = row.get("kb_budget_max")
            if max_calls is None:
                return None
            used = int(row.get("kb_budget_used") or 0)
            cap = max(0, int(max_calls))
            if used >= cap:
                return f"orientg_kb_ask budget exhausted (max {cap} per session)"
            conn.execute(upd, {"k": key})
        return None
    except Exception:
        logger.debug("consume kb budget db failed for %s", key, exc_info=True)
        return None


def reset_for_tests() -> None:
    init_hermes_session_store_table()
    try:
        with engine.connect() as conn:
            conn.execute(text("DELETE FROM hermes_session_store"))
            conn.commit()
    except Exception:
        pass
