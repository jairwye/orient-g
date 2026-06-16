"""Orient-G Agent 呈现策略与无 KB 路由。"""

from __future__ import annotations

import json

from backend.services.agent_kb_router import AgentRoute, resolve_agent_route
from backend.services.hermes_client import _build_messages
from backend.services.orientg_agent_presentation import (
    fix_glued_markdown_lists,
    infer_reply_language,
    orientg_agent_presentation_context,
)


def test_infer_reply_language_zh():
    assert infer_reply_language("你能做什么") == "zh"
    assert infer_reply_language("hello 你好") == "zh"


def test_infer_reply_language_en():
    assert infer_reply_language("What can you do?") == "en"


def test_no_kb_fast_mode_still_hermes_lite():
    got = resolve_agent_route(
        user_query="你能做什么",
        agent_mode="fast",
        allow_kb_write=False,
        has_kb_scope=False,
        prefetch_result=None,
        hermes_configured=True,
    )
    assert got == AgentRoute.hermes_lite


def test_build_messages_includes_presentation_for_no_kb():
    msgs = _build_messages(
        [{"role": "user", "content": "你能做什么"}],
        username="u1",
        kb_scope={},
        allow_kb_write=False,
        attached_doc_ids=None,
        hermes_session_id="hs1",
        orientg_route="hermes_lite",
    )
    payload = json.loads(msgs[0]["content"].split("\n", 1)[1])
    assert payload.get("orientg_kb_scope_empty") is True
    assert payload.get("orientg_reply_language") == "zh-CN"
    assert "简体中文" in payload.get("orientg_reply_language_rule", "")
    assert "orientg_product_intro_scope" in payload
    req = payload.get("orientg_answer_requirements") or ""
    assert "Markdown" in req
    assert "Orient-G" in req or "知识库" in req


def test_fix_glued_markdown_lists():
    raw = "**任务执行**-编写、调试-执行终端命令"
    out = fix_glued_markdown_lists(raw)
    assert "**任务执行**" in out
    assert "\n" in out
    assert "- 编写" in out


def test_build_messages_no_kb_skips_kb_mcp_tools():
    msgs = _build_messages(
        [{"role": "user", "content": "你能做什么"}],
        username="u1",
        kb_scope={},
        allow_kb_write=False,
        attached_doc_ids=None,
        hermes_session_id="hs1",
        orientg_route="hermes_lite",
    )
    payload = json.loads(msgs[0]["content"].split("\n", 1)[1])
    assert payload.get("orientg_allowed_kb_tools") == []
    assert "勿调用 orientg_kb" in payload.get("orientg_tool_policy", "")


def test_kb_scope_fast_mode_unchanged_tier0():
    """已选知识库 + 快速：仍为 Tier 0，不受无 KB 规则影响。"""
    got = resolve_agent_route(
        user_query="华清25年营收是多少",
        agent_mode="fast",
        allow_kb_write=False,
        has_kb_scope=True,
        prefetch_result={"ok": True, "citations": [{"doc_id": "d1"}]},
        hermes_configured=True,
    )
    assert got == AgentRoute.fast
