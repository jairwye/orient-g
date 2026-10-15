"""breakdown/compare 预检索时 Hermes delta 应映射为 thinking，终稿才进主气泡。"""

from __future__ import annotations

import json
import re
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


@patch("backend.services.agent_kb_supplemental.run_supplemental_kb_asks")
@patch("backend.routers.agent.stream_agent_chat")
def test_hermes_full_error_runs_tier2_recovery_instead_of_bare_error(mock_stream, mock_sup_kb):
    mock_stream.return_value = iter(
        [{"type": "error", "message": "Hermes Runs 已超过 120 秒无数据。", "code": "hermes_stall"}]
    )
    mock_sup_kb.return_value = (
        {
            **PREFETCH,
            "reply": "恢复后答案：人员结构对比",
            "kb_supplemental": True,
        },
        [{"name": "orientg_kb_ask", "status": "ok", "supplemental": True, "query": "q"}],
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
    assert any(e.get("step") == "tier2_error_recovery" for e in evts)
    done = [e for e in evts if e.get("type") == "done"][-1]
    assert done.get("tier2_error_recovery") is True
    assert not any(e.get("type") == "error" and e.get("code") == "hermes_stall" for e in evts)


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


PERSONNEL_LITE_QUERY = "对比分析YYCQ和可比公司A25年的人员结构"
PERSONNEL_LITE_DRAFT = (
    "两次MCP检索已完成。现在撰写终稿。\n"
    "## 人员结构对照\n"
    "| 职能归属 | 可比公司A | YYCQ |\n"
    "|----------|----------|----------|\n"
    "| 研发 | 1,378 | 70 |\n"
    "| 销售 | 946 | 证据未覆盖 |\n"
    "| 运营 | 242 | 61 |\n"
    "| 管理 | 36 | 33 |\n"
    "| 支持 | 115 | 46 |\n"
    "| **员工合计** | **3,138** | **约210** |\n\n"
    "## 对比分析\n"
    "规模差异：可比公司A员工总数3,138人，YYCQ约210人。\n"
    "研发导向：可比公司A研发1,378人；YYCQ研发70人。\n"
    "## 口径说明\n"
    "YYCQ为 excel 分项加总（分项合计 210）；可比公司A为年报口径。\n"
)


@patch("backend.routers.agent.synthesize_kb_reply")
@patch("backend.routers.agent.stream_agent_chat")
def test_hermes_lite_stall_salvages_personnel_draft_without_money(mock_stream, mock_synth):
    """A2：Hermes lite 空转/stall 时须 salvage 人员过程稿并剥离约N，不得被金额尺子拒收。"""
    chunks = [PERSONNEL_LITE_DRAFT[i : i + 90] for i in range(0, len(PERSONNEL_LITE_DRAFT), 90)]
    mock_stream.return_value = iter(
        [{"type": "delta", "content": c} for c in chunks]
        + [{"type": "error", "message": "Hermes Runs 已超过 480 秒无数据。", "code": "hermes_stall"}]
    )
    mock_synth.return_value = {
        "reply": "本地模板：人员结构对照占位（勿采用）。",
        "citations": [{"doc_id": "ud_x"}],
        "synthesis": "local",
    }
    raw = list(
        _agent_chat_stream_events(
            token="tok",
            uname="finance_test",
            tenant_id="tenant1",
            messages=[{"role": "user", "content": PERSONNEL_LITE_QUERY}],
            kb_scope_payload={"selected_folder_ids": ["f1"]},
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
            prefetch_tool_calls=[{"name": "orientg_kb_ask", "status": "ok", "prefetch": True}],
            prefetch_result={
                "ok": True,
                "citations": [{"doc_id": "ud_x"}],
                "evidence_pack": {
                    "task_type": "compare",
                    "coverage_score": 0.9,
                    "gaps": [],
                },
            },
            fixtures={"tenant_id": "tenant1", "documents": []},
            agent_route=AgentRoute.hermes_lite,
        )
    )
    evts = _parse_sse(raw)
    done = [e for e in evts if e.get("type") == "done"][-1]
    reply = done.get("reply") or ""
    assert done.get("hermes_salvaged") is True or done.get("structured_gate_applied") is True
    assert "人员结构对照" in reply
    assert "YYCQ" in reply
    assert "可比公司A" in reply
    assert "946" in reply and "242" in reply
    assert re.search(r"1[,，]?378", reply)
    assert "约210" not in reply
    assert "本地模板" not in reply
    assert not any(e.get("type") == "error" and e.get("code") == "hermes_stall" for e in evts)


@patch("backend.routers.agent.stream_agent_chat")
@patch("backend.services.agent_kb_supplemental.iter_supplemental_revision_events")
def test_personnel_rich_final_kb0_money_pack_keeps_hermes_no_supplemental(
    mock_sup, mock_stream, monkeypatch
):
    """手测：合格人员终稿 + kb=0 + prefetch 混入费用金额 → 禁补检索×N，禁门禁顶替。"""
    from backend.config import settings

    monkeypatch.setattr(settings, "hermes_native_mcp_reply", True)
    monkeypatch.setattr(settings, "hermes_native_skip_supplemental", True)

    rich = (
        "## 人员结构对照\n"
        "| 职能 | 可比公司A | YYCQ |\n"
        "| --- | --- | --- |\n"
        "| 员工总数（年报） | 3,138 | 139 |\n"
        "| 研发 | 1,378 | 70 |\n"
        "| 销售 | 946 | 证据未覆盖 |\n"
        "| 运营 | 242 | 61 |\n"
        "| 管理 | 36 | 33.15 |\n"
        "| 支持 | 115 | 45.85 |\n\n"
        "### 对比分析\n"
        "1. 规模口径不同。2. 研发双口径。3. 学历。4. 年龄。5. 职能重心。\n"
        "### 口径说明\n可比公司A=年报；YYCQ=excel。\n"
    )
    mock_stream.return_value = iter(
        [
            {
                "type": "status",
                "message": "已有合格 Hermes 终稿，跳过「未调 MCP」优先重试",
                "step": "hermes_skip_mcp_retry_user_facing",
            },
            {
                "type": "status",
                "message": "人员横比 MCP 核证门闸：kb=0 abort=False/- native=True … want=False",
                "step": "hermes_mcp_verify_gate",
            },
            {"type": "delta", "content": rich},
            {
                "type": "done",
                "reply": rich,
                "hermes_stream_stats": {
                    "hermes_orientg_kb_ask_calls": 0,
                    "orientg_kb_ask_calls": 0,
                    "gateway_orientg_kb_ask_calls": 1,
                },
            },
        ]
    )
    mock_sup.side_effect = AssertionError(
        "qualified personnel final + kb=0 must not run money-pack supplemental×N"
    )
    money_excerpt = (
        "销售费用合计 13,722,360.23元；广告费 1,234,567.89元；"
        "职工薪酬 2,345,678.90元；差旅费 345,678.12元；业务招待费 456,789.01元"
    )
    raw = list(
        _agent_chat_stream_events(
            token="tok",
            uname="finance_test",
            tenant_id="tenant1",
            messages=[{"role": "user", "content": PERSONNEL_LITE_QUERY}],
            kb_scope_payload={"selected_folder_ids": ["f1"]},
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
            prefetch_tool_calls=[
                {"name": "orientg_kb_ask", "status": "ok", "prefetch": True}
            ],
            prefetch_result={
                "ok": True,
                "citations": [{"doc_id": "ud_a"}, {"doc_id": "ud_b"}],
                "evidence_pack": {
                    "task_type": "compare",
                    "coverage_score": 0.55,
                    "gaps": ["销售人员"],
                    "facets": [{"label": "费用分项", "excerpt": money_excerpt}],
                },
            },
            fixtures={"tenant_id": "tenant1", "documents": []},
            agent_route=AgentRoute.hermes_full,
        )
    )
    evts = _parse_sse(raw)
    assert mock_sup.call_count == 0
    assert not any(
        "自动执行定向" in str(e.get("message") or "")
        or "未调用 MCP 补检索" in str(e.get("message") or "")
        for e in evts
    )
    done = [e for e in evts if e.get("type") == "done"][-1]
    assert not done.get("kb_supplemental")
    assert not done.get("structured_gate_applied")
    reply = str(done.get("reply") or "")
    assert "人员结构对照" in reply
    assert "1,378" in reply or "1378" in reply
    assert "研发双口径" in reply or "口径说明" in reply
    # 不得被薄门禁模板顶替（仅 33.15/45.85/210 而无丰富分析）
    assert "学历" in reply or "年龄" in reply or "职能重心" in reply or "研发双口径" in reply
    src = str(done.get("reply_source") or done.get("synthesis") or "")
    assert "gate" not in src.lower() or src in ("hermes", "")


@patch("backend.routers.agent.stream_agent_chat")
@patch("backend.services.agent_kb_supplemental.iter_supplemental_revision_events")
def test_substantive_process_draft_kb0_skips_supplemental_chain(mock_sup, mock_stream):
    """手测毁流路径：实质过程稿 + kb=0 → 禁「未调 MCP 补检索」链，流须正常收束。"""
    process = (
        "首轮取证完成。可比公司A研发人员1378人，YYCQ70人。"
        "正在做核证补缺计划后撰写终稿。evidence_sufficient=false"
    )
    mock_stream.return_value = iter(
        [
            {
                "type": "status",
                "message": "已有实质 Hermes 过程稿，跳过「未调 MCP」优先重试（避免清稿毁流）",
                "step": "hermes_skip_mcp_retry_substantive_draft",
            },
            {"type": "delta", "content": process},
            {
                "type": "done",
                "reply": process,
                "hermes_stream_stats": {
                    "hermes_orientg_kb_ask_calls": 0,
                    "orientg_kb_ask_calls": 0,
                    "gateway_orientg_kb_ask_calls": 0,
                },
            },
        ]
    )
    mock_sup.side_effect = AssertionError(
        "substantive process draft + kb=0 must not run no-MCP supplemental×N"
    )

    raw = list(
        _agent_chat_stream_events(
            token="tok",
            uname="finance_test",
            tenant_id="tenant1",
            messages=[
                {
                    "role": "user",
                    "content": "对比分析YYCQ和可比公司A25年的人员结构",
                }
            ],
            kb_scope_payload={"selected_folder_ids": ["f1"]},
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
            prefetch_tool_calls=[
                {"name": "orientg_kb_ask", "status": "ok", "prefetch": True}
            ],
            prefetch_result={
                "ok": True,
                "citations": [{"doc_id": "ud_x"}],
                "evidence_pack": {
                    "task_type": "compare",
                    "coverage_score": 0.9,
                    "gaps": ["x"],
                },
            },
            fixtures={"tenant_id": "tenant1", "documents": []},
            agent_route=AgentRoute.hermes_full,
        )
    )
    evts = _parse_sse(raw)
    assert mock_sup.call_count == 0
    assert not any(
        "自动执行定向" in str(e.get("message") or "")
        or "未调用 MCP 补检索" in str(e.get("message") or "")
        for e in evts
    )
    assert not any(e.get("type") == "error" for e in evts)
    done = [e for e in evts if e.get("type") == "done"][-1]
    assert not done.get("kb_supplemental")
    reply = str(done.get("reply") or "")
    assert reply.strip()
    # 过程稿非终稿：允许未成稿说明或 salvage/门禁表；禁止空白毁流
    assert (
        "人员结构对照" in reply
        or "未完成可用终稿" in reply
        or "证据不足" in reply
        or "1378" in reply
    )


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
