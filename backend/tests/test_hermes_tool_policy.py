"""Hermes system 上下文：Tier 1 禁用 terminal。"""

from backend.services.hermes_client import _build_messages


def test_hermes_lite_forbids_terminal_in_context():
    msgs = _build_messages(
        [{"role": "user", "content": "查费用"}],
        username="u1",
        kb_scope={"selected_folder_ids": ["f1"]},
        allow_kb_write=False,
        attached_doc_ids=None,
        hermes_session_id="hs1",
        orientg_route="hermes_lite",
        orientg_kb_ask_budget=2,
    )
    system = msgs[0]["content"]
    assert "orientg_forbidden_tools" in system
    assert "terminal" in system
    assert "orientg_tool_policy" in system
