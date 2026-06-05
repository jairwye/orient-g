"""breakdown/compare 预检索时 Hermes delta 应映射为 thinking，终稿才进主气泡。"""

from __future__ import annotations

import json
from unittest.mock import patch

from backend.routers.agent import _agent_chat_stream_events
from backend.services.agent_kb_router import AgentRoute


PREFETCH = {
    "ok": True,
    "citations": [{"doc_id": "ud_x"}],
    "evidence_pack": {"task_type": "compare", "coverage_score": 1.0},
}


def _parse_sse(events: list[str]) -> list[dict]:
    out: list[dict] = []
    for block in events:
        for line in block.strip().split("\n"):
            if not line.startswith("data:"):
                continue
            raw = line[5:].strip()
            if raw == "[DONE]":
                continue
            out.append(json.loads(raw))
    return out


@patch("backend.routers.agent.stream_agent_chat")
@patch("backend.services.agent_kb_supplemental.iter_supplemental_revision_events")
def test_hermes_delta_deferred_to_thinking_before_supplemental(mock_sup, mock_stream):
    mock_stream.return_value = iter(
        [
            {"type": "delta", "content": "中间稿：缺少附注明细"},
            {"type": "done", "reply": "中间稿：缺少附注明细", "hermes_stream_stats": {"orientg_kb_ask_calls": 0}},
        ]
    )

    def _fake_sup(**kwargs):
        yield {"type": "status", "message": "补检索…", "step": "supplemental_synth"}
        yield {"type": "replace_reply", "content": "终稿：职工薪酬 10,802,366.11"}
        yield {
            "type": "supplemental_meta",
            "reply": "终稿：职工薪酬 10,802,366.11",
            "citations": [{"doc_id": "ud_fee"}],
            "tool_calls": [],
            "prefetch_result": PREFETCH,
            "synthesis": "local_llm",
            "supplemental_adopted": True,
        }

    mock_sup.side_effect = _fake_sup

    raw = list(
        _agent_chat_stream_events(
            token="tok",
            uname="finance_test",
            tenant_id="tenant1",
            messages=[{"role": "user", "content": "华清25、24两年销售费用明细对比"}],
            kb_scope_payload={"selected_folder_ids": ["f1"]},
            attached=[],
            body=type("B", (), {"allow_kb_write": False, "enabled_skills": None, "model": None, "hermes_session_id": None, "orientg_chat_session_id": None})(),
            prefetch_tool_calls=[{"name": "orientg_kb_ask", "status": "ok", "prefetch": True}],
            prefetch_result=PREFETCH,
            fixtures={"tenant_id": "tenant1", "documents": []},
            agent_route=AgentRoute.hermes_lite,
        )
    )
    evts = _parse_sse(raw)
    types = [e.get("type") for e in evts]
    assert "thinking" in types
    assert types.count("delta") == 0
    assert any(e.get("type") == "replace_reply" and "职工薪酬" in str(e.get("content")) for e in evts)
    done = [e for e in evts if e.get("type") == "done"][-1]
    assert "职工薪酬" in (done.get("reply") or "")


@patch("backend.routers.agent.stream_agent_chat")
def test_hermes_full_error_does_not_local_fallback(mock_stream):
    mock_stream.return_value = iter(
        [{"type": "error", "message": "Hermes Runs 已超过 120 秒无数据。", "code": "hermes_stall"}]
    )
    raw = list(
        _agent_chat_stream_events(
            token="tok",
            uname="finance_test",
            tenant_id="tenant1",
            messages=[{"role": "user", "content": "华清25、24两年研发费用明细对比"}],
            kb_scope_payload={"selected_folder_ids": ["f1"]},
            attached=[],
            body=type("B", (), {"allow_kb_write": False, "enabled_skills": None, "model": None, "hermes_session_id": None, "orientg_chat_session_id": None})(),
            prefetch_tool_calls=[{"name": "orientg_kb_ask", "status": "ok", "prefetch": True}],
            prefetch_result=PREFETCH,
            fixtures={"tenant_id": "tenant1", "documents": []},
            agent_route=AgentRoute.hermes_full,
        )
    )
    evts = _parse_sse(raw)
    assert any(e.get("type") == "error" for e in evts)
    assert not any(e.get("type") == "done" and e.get("hermes_fallback") for e in evts)
