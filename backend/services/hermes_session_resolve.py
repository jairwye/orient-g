"""Orient-G 智能体会话 ↔ Hermes session_key（按用户隔离）。"""

from __future__ import annotations

import re
import uuid

from backend.services.hermes_token_bridge import normalize_session_key


def _safe_segment(value: str, *, max_len: int) -> str:
    s = re.sub(r"[^a-zA-Z0-9_-]+", "_", (value or "").strip())
    return s[:max_len] if s else ""


def resolve_hermes_session_key(
    *,
    username: str,
    hermes_session_id: str | None = None,
    orientg_chat_session_id: str | None = None,
) -> str:
    """
    解析 Hermes session_key（带 orientg- 前缀）。

    优先级：
    1. 客户端已持久化的 hermes_session_id（同智能体历史续聊）
    2. orientg_chat_session_id + username（同 Orient-G 会话首条即可稳定，不必等 done）
    3. 新随机 UUID（无会话锚点时）
    """
    explicit = normalize_session_key(hermes_session_id or "")
    if explicit:
        return explicit
    user = _safe_segment(username, max_len=48)
    chat = _safe_segment(orientg_chat_session_id or "", max_len=96)
    if user and chat:
        return normalize_session_key(f"{user}--{chat}")
    return normalize_session_key(str(uuid.uuid4()))
