"""Hermes Orient-G KB 工具策略执行层。"""

from backend.services.hermes_client import guard_kb_forbidden_tool_sse, _build_messages
from backend.services.hermes_orientg_policy import (
    is_forbidden_kb_tool,
    orientg_route_is_kb_task,
    tool_progress_looks_like_shell,
)


def test_orientg_route_is_kb_task():
    assert orientg_route_is_kb_task("hermes_lite")
    assert orientg_route_is_kb_task("hermes_full")
    assert not orientg_route_is_kb_task("fast")


def test_is_forbidden_kb_tool():
    assert is_forbidden_kb_tool("terminal")
    assert is_forbidden_kb_tool("terminal.run")
    assert not is_forbidden_kb_tool("orientg_kb_ask")


def test_tool_progress_shell_patterns():
    assert tool_progress_looks_like_shell("curl http://localhost/api/agent/chat")
    assert tool_progress_looks_like_shell("import urllib.request")
    assert not tool_progress_looks_like_shell("orientg_kb_ask query=费用")


def test_guard_blocks_terminal_tool_progress():
    blocked = guard_kb_forbidden_tool_sse(
        {"type": "tool_progress", "status": "running", "tool": "terminal", "message": "ls"},
        orientg_route="hermes_lite",
    )
    assert blocked is not None
    assert blocked.get("type") == "tool_progress"
    assert blocked.get("status") == "failed"


def test_build_messages_omits_import_when_write_disabled():
    msgs = _build_messages(
        [{"role": "user", "content": "写报告"}],
        username="u1",
        kb_scope={"selected_folder_ids": ["f1"]},
        allow_kb_write=False,
        attached_doc_ids=None,
        hermes_session_id="hs1",
        orientg_route="hermes_full",
    )
    system = msgs[0]["content"]
    assert "orientg_kb_import_artifact" not in system
    assert '"orientg_kb_write": false' in system or "orientg_kb_write" in system
