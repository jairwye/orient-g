"""breakdown/compare 预检索时 Hermes delta 应映射为 thinking，终稿才进主气泡。"""

from __future__ import annotations

import json
from unittest.mock import patch

from backend.routers.agent import _agent_chat_stream_events
from backend.services.agent_kb_router import AgentRoute


PREFETCH = {
    "ok": True,
    "citations": [{"doc_id": "ud_x"}],
    "evidence_pack": {"task_type": "breakdown", "coverage_score": 1.0},
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
            messages=[{"role": "user", "content": "可比E25、24两年销售费用明细对比"}],
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


BREAKDOWN_PREFETCH = {
    "ok": True,
    "citations": [{"doc_id": "ud_x"}],
    "evidence_pack": {
        "task_type": "breakdown",
        "coverage_score": 1.0,
        "facets": [
            {
                "label": "附注",
                "excerpt": "职工薪酬 30,678,824.83 折旧 7,624,220.17 合计 44,933,044.34",
            }
        ],
    },
}


@patch("backend.routers.agent.stream_agent_chat")
@patch("backend.services.agent_kb_supplemental.iter_supplemental_revision_events")
def test_tier2_deferred_draft_skips_supplemental_when_rich_hermes(mock_sup, mock_stream):
    """过程稿 defer 时须用累积正文做 supplemental 判定，勿因 done.reply 为空误触发本地 synth。"""
    long_draft = (
        "## 可比公司E管理费用对比分析报告\n\n"
        "结论：管理费用 44,933,044.34 元。\n\n"
        "| 管理费用 | 44,933,044.34 | 52,950,207.05 |\n"
        "| 职工薪酬 | 30,678,824.83 | 32,439,022.86 |\n\n"
        "#### 变动原因\n"
        "主要系使用权资产减少，租赁面积缩减。\n"
        "盈利能力影响：费比改善。\n" * 80
    )
    mock_stream.return_value = iter(
        [
            {"type": "delta", "content": long_draft},
            {"type": "done", "reply": "", "hermes_stream_stats": {"orientg_kb_ask_calls": 0}},
        ]
    )
    mock_sup.side_effect = AssertionError("tier2 rich deferred draft must not run supplemental")

    raw = list(
        _agent_chat_stream_events(
            token="tok",
            uname="finance_test",
            tenant_id="tenant1",
            messages=[{"role": "user", "content": "出一份可比E25、24两年管理费用明细的对比分析报告"}],
            kb_scope_payload={"selected_folder_ids": ["f1"]},
            attached=[],
            body=type("B", (), {"allow_kb_write": False, "enabled_skills": None, "model": None, "hermes_session_id": None, "orientg_chat_session_id": None})(),
            prefetch_tool_calls=[{"name": "orientg_kb_ask", "status": "ok", "prefetch": True}],
            prefetch_result=BREAKDOWN_PREFETCH,
            fixtures={"tenant_id": "tenant1", "documents": []},
            agent_route=AgentRoute.hermes_full,
        )
    )
    evts = _parse_sse(raw)
    done = [e for e in evts if e.get("type") == "done"][-1]
    assert not done.get("kb_supplemental")
    assert "44,933,044.34" in (done.get("reply") or "")
    assert len(done.get("reply") or "") > 1500


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
            messages=[{"role": "user", "content": "可比E25、24两年研发费用明细对比"}],
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


@patch("backend.routers.agent.synthesize_kb_reply")
@patch("backend.routers.agent.stream_agent_chat")
def test_hermes_lite_error_salvages_rich_draft_over_synth(mock_stream, mock_synth):
    long_draft = (
        "## 可比公司E管理费用对比分析报告\n\n"
        "| 指标 | 2025年 | 2024年 |\n|---|---|---|\n"
        "| 管理费用合计 | 44,933,044.34 | 52,950,207.05 |\n"
        "| 职工薪酬 | 30,678,824.83 | 32,439,022.86 |\n"
        "## 变动原因\n折旧及摊销费用减少 5,156,810.93 元，职工薪酬减少 1,760,198.03 元。\n"
        + ("补充说明段落。" * 40)
    )
    chunks = [long_draft[i : i + 80] for i in range(0, len(long_draft), 80)]
    mock_stream.return_value = iter(
        [{"type": "delta", "content": c} for c in chunks]
        + [{"type": "error", "message": "Hermes stall", "code": "hermes_stall"}]
    )
    mock_synth.return_value = {
        "reply": "证据未提供管理费用变动的具体原因说明，仅列示金额。",
        "citations": [{"doc_id": "ud_x"}],
        "synthesis": "local",
    }
    raw = list(
        _agent_chat_stream_events(
            token="tok",
            uname="finance_test",
            tenant_id="tenant1",
            messages=[{"role": "user", "content": "可比E25、24两年管理费用明细对比"}],
            kb_scope_payload={"selected_folder_ids": ["f1"]},
            attached=[],
            body=type("B", (), {"allow_kb_write": False, "enabled_skills": None, "model": None, "hermes_session_id": None, "orientg_chat_session_id": None})(),
            prefetch_tool_calls=[{"name": "orientg_kb_ask", "status": "ok", "prefetch": True}],
            prefetch_result={
                **PREFETCH,
                "evidence_pack": {
                    **PREFETCH["evidence_pack"],
                    "gaps": [],
                    "coverage_score": 1.0,
                },
            },
            fixtures={"tenant_id": "tenant1", "documents": []},
            agent_route=AgentRoute.hermes_lite,
        )
    )
    evts = _parse_sse(raw)
    done = [e for e in evts if e.get("type") == "done"][-1]
    assert done.get("hermes_salvaged") is True
    assert "44,933,044.34" in (done.get("reply") or "")
    assert "证据未提供" not in (done.get("reply") or "")


@patch("backend.services.ai_interaction_llm.generate_chat_reply")
@patch("backend.routers.agent.settings")
@patch("backend.routers.agent.stream_agent_chat")
def test_hermes_empty_without_kb_scope_falls_back_to_local_llm(mock_stream, mock_settings, mock_chat):
    mock_settings.chat_llm_available = True
    mock_settings.llm_chat_configured = True
    mock_settings.llm_model = "test-model"
    mock_settings.ollama_model = "ollama-model"
    mock_stream.return_value = iter(
        [{"type": "error", "message": "Hermes 已完成编排，但未生成可展示的正文。", "code": "hermes_empty"}]
    )
    mock_chat.return_value = "你好，我是本地 LLM 回答。"
    raw = list(
        _agent_chat_stream_events(
            token="tok",
            uname="finance_test",
            tenant_id="tenant1",
            messages=[{"role": "user", "content": "你好"}],
            kb_scope_payload={},
            attached=[],
            body=type(
                "B",
                (),
                {
                    "allow_kb_write": False,
                    "enabled_skills": None,
                    "model": None,
                    "hermes_session_id": None,
                    "orientg_chat_session_id": None,
                },
            )(),
            prefetch_tool_calls=[],
            prefetch_result=None,
            fixtures={"tenant_id": "tenant1", "documents": []},
            agent_route=AgentRoute.hermes_lite,
        )
    )
    evts = _parse_sse(raw)
    done = [e for e in evts if e.get("type") == "done"][-1]
    assert done.get("hermes_fallback") is True
    assert done.get("synthesis") == "local_llm"
    assert "本地 LLM" in (done.get("reply") or "")
    mock_chat.assert_called_once()
