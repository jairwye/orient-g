"""Orient-G × Hermes KB 任务工具策略（执行层与 prompt 共用）。"""

from __future__ import annotations

import re

KB_FORBIDDEN_TOOL_NAMES: tuple[str, ...] = (
    "terminal",
    "read_file",
    "grep",
    "glob",
    "find",
    "execute_code",
    "session_search",
    "session-search",
    "skill_view",
    "orientg-debugging",
    "browser",
    "web_search",
    "websearch",
    "web-tools",
    "web_tools",
    "webtools",
    "memory",
    "searxng",
    "search_web",
    "navigate",
    "browse",
    "playwright",
    "puppeteer",
)

_SHELL_LOOPBACK_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bcurl\b", re.I),
    re.compile(r"\bimport urllib\b", re.I),
    re.compile(r"/api/agent/chat", re.I),
    re.compile(r"\bwget\b", re.I),
    re.compile(r"python\.exe\s+-c\b", re.I),
    re.compile(r"\.venv[\\/]Scripts[\\/]python", re.I),
    re.compile(r"\borientg_mcp_tools\b", re.I),
    re.compile(r"\bsubprocess\b", re.I),
    re.compile(r"\bcat\b.*\.md", re.I),
    re.compile(r"\btype\b.*\.md", re.I),
    re.compile(r"uploads[\\/]", re.I),
    re.compile(r"行业财报汇析", re.I),
)

_WEB_BROWSE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"https?://", re.I),
    re.compile(r"\bbaidu\.com\b", re.I),
    re.compile(r"\bgoogle\.", re.I),
    re.compile(r"\bcninfo\.com", re.I),
    re.compile(r"\beastmoney\.com", re.I),
    re.compile(r"\bsina\.com", re.I),
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


def tool_progress_looks_like_web(message: str | None, tool_name: str | None = None) -> bool:
    text = f"{tool_name or ''} {message or ''}".strip()
    if not text:
        return False
    if is_forbidden_kb_tool(tool_name):
        return True
    return any(p.search(text) for p in _WEB_BROWSE_PATTERNS)


def kb_forbidden_tool_message(
    *,
    session_key: str = "",
    user_query: str = "",
    evidence_ready: bool = False,
) -> str:
    from backend.services.hermes_kb_mcp_bridge import kb_ask_tool_invocation_hint

    hint = kb_ask_tool_invocation_hint(session_key=session_key, user_query=user_query)
    ex = hint.get("example") or {}
    tool_display = hint.get("name") or "orientg_kb_ask"
    hermes_tool = hint.get("hermes_tool_name") or "mcp__orientg__orientg_kb_ask"
    ban = (
        "KB 任务禁止 terminal/shell/execute_code/session_search/浏览器/外网搜索/memory/web-tools 空转。"
    )
    if evidence_ready:
        return (
            ban
            + "已有 MCP 返回时：直接阅读证据节选/agent_payload 文本，用中文写终稿；"
            "严禁 execute_code/shell/session_search 解析 JSON。"
            f"若仍缺证据再调 {hermes_tool}（不同 query）。"
        )
    return (
        ban
        + f"请直接调用 MCP 工具 {hermes_tool}（{tool_display}），"
        f"示例参数 query={ex.get('query')!r}、hermes_session_key={ex.get('hermes_session_key')!r}。"
        "收到 MCP 文本后直接中文成稿，勿用代码解析。"
    )


def kb_route_allowed_toolsets(orientg_route: str | None) -> list[str] | None:
    if not orientg_route_is_kb_task(orientg_route):
        return None
    return ["orientg"]
