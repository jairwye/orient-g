"""Orient-G × Hermes KB 任务工具策略（执行层与 prompt 共用）。"""

from __future__ import annotations

import re

# KB 问答 / 深度编排（hermes_lite | hermes_full）禁止的工具名（子串匹配）
KB_FORBIDDEN_TOOL_NAMES: tuple[str, ...] = (
    "terminal",
    "execute_code",
    "skill_view",
    "orientg-debugging",
)

# 工具 progress 消息中暗示 shell/loopback 的模式
_SHELL_LOOPBACK_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bcurl\b", re.I),
    re.compile(r"\bimport urllib\b", re.I),
    re.compile(r"/api/agent/chat", re.I),
    re.compile(r"\bwget\b", re.I),
)


def orientg_route_is_kb_task(orientg_route: str | None) -> bool:
    r = (orientg_route or "").strip().lower()
    return r in ("hermes_lite", "hermes_full")


def is_forbidden_kb_tool(tool_name: str | None) -> bool:
    name = (tool_name or "").strip().lower()
    if not name:
        return False
    return any(f in name for f in KB_FORBIDDEN_TOOL_NAMES)


def tool_progress_looks_like_shell(message: str | None) -> bool:
    text = (message or "").strip()
    if not text:
        return False
    return any(p.search(text) for p in _SHELL_LOOPBACK_PATTERNS)


def kb_route_allowed_toolsets(orientg_route: str | None) -> list[str] | None:
    """Hermes Runs/Chat 可选 toolsets 白名单（不含 terminal）。"""
    if not orientg_route_is_kb_task(orientg_route):
        return None
    return ["orientg", "file", "mcp"]
