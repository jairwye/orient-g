"""全局 Hermes 主答 authorship：深度编排终稿须 reply_source=hermes。

人员对比仅为回归样例；本文件锁定通用路径（forbidden_loop 不得门禁顶替）。
"""

from __future__ import annotations


FINANCE_QUERY = "对比分析YYCQ和可比公司A2025年销售费用明细"
PERSONNEL_QUERY = "对比分析YYCQ和可比公司A25年的人员结构"


def test_session_search_is_forbidden_kb_tool():
    from backend.services.hermes_orientg_policy import is_forbidden_kb_tool

    assert is_forbidden_kb_tool("session_search")
    assert is_forbidden_kb_tool("session-search")


def test_kb_forbidden_message_urges_write_final_when_evidence_ready():
    from backend.services.hermes_orientg_policy import kb_forbidden_tool_message

    msg = kb_forbidden_tool_message(
        session_key="sk1",
        user_query=FINANCE_QUERY,
        evidence_ready=True,
    )
    assert "execute_code" in msg
    assert "直接" in msg and ("成稿" in msg or "中文" in msg)
    assert "MCP" in msg
    # 全局口径：勿写成「仅人员」特例
    assert "仅人员" not in msg


def test_loop_guard_forbidden_with_kb_asks_write_final_code():
    """已有 MCP 取证后，forbidden 收束应导向成稿，而非门禁顶替。"""
    from backend.services.hermes_runs_loop_guard import HermesRunsLoopGuard

    g = HermesRunsLoopGuard(orientg_route="hermes_full", max_forbidden_blocks=3)
    g.sync_stats({"hermes_orientg_kb_ask_calls": 2})
    g.on_forbidden_block()
    g.on_forbidden_block()
    assert not g.should_abort()[0]
    g.on_forbidden_block()
    abort, code, msg = g.should_abort()
    assert abort
    assert code == "hermes_forbidden_write_final"
    assert "成稿" in msg or "MCP" in msg


def test_loop_guard_forbidden_without_kb_still_forbidden_loop():
    from backend.services.hermes_runs_loop_guard import HermesRunsLoopGuard

    g = HermesRunsLoopGuard(orientg_route="hermes_full", max_forbidden_blocks=3)
    for _ in range(3):
        g.on_forbidden_block()
    abort, code, _msg = g.should_abort()
    assert abort
    assert code == "hermes_run_forbidden_loop"


def test_build_mcp_write_final_runs_body_global():
    from backend.services.hermes_kb_mcp_bridge import build_mcp_write_final_runs_body

    body = build_mcp_write_final_runs_body(
        user_query=FINANCE_QUERY,
        session_key="sk-wf-1",
        model="hermes-agent",
    )
    instr = str(body.get("instructions") or "")
    assert body["toolsets"] == ["orientg"]
    assert body["session_id"] == "sk-wf-1"
    assert FINANCE_QUERY in str(body.get("input") or "") or FINANCE_QUERY[:8] in instr
    assert "成稿" in instr or "中文" in instr
    assert "execute_code" in instr
    assert "仅人员" not in instr


def test_resolve_hermes_reply_source_defaults_hermes():
    from backend.services.agent_kb_supplemental import resolve_hermes_reply_source

    meta = resolve_hermes_reply_source(
        structured_gate_applied=False,
        misattribution_gate_applied=False,
        supplemental_ran=False,
        supplemental_adopted=False,
        reply="## 销售费用对比\n两家 2025 销售费用分项见年报，YYCQ 与可比公司A 口径不同。\n",
    )
    assert meta["reply_source"] == "hermes"


def test_resolve_hermes_reply_source_salvaged_is_hermes():
    """中断 salvage 的 Hermes 实质成稿仍算 Hermes 主答。"""
    from backend.services.agent_kb_supplemental import resolve_hermes_reply_source

    meta = resolve_hermes_reply_source(
        hermes_salvaged=True,
        structured_gate_applied=False,
        reply="## 费用对比\n销售费用分项：广告 1.2 亿；工资 0.8 亿。\n",
    )
    assert meta["reply_source"] == "hermes"


PROCESS_DRAFT_ONLY = (
    "Let me first retrieve the personnel structure for both companies via orientg_kb_ask.\n\n"
    "首轮 MCP 已返回 agent_payload，evidence_sufficient=false。\n"
    "核证补缺计划：\n"
    "1. verification_queries: 可比公司A 2025 研发人员；YYCQ 人员结构\n"
    "2. next_action=verify_gap_then_write_final\n"
    "我将继续调用 orientg_kb_ask 补齐后再撰写终稿。\n"
)


def test_resolve_hermes_reply_source_rejects_process_draft_as_hermes():
    """过程稿（英文 planning + 核证计划）不得标 reply_source=hermes。"""
    from backend.services.agent_kb_supplemental import resolve_hermes_reply_source
    from backend.services.hermes_response_analysis import hermes_reply_is_user_facing_final

    assert not hermes_reply_is_user_facing_final(
        PROCESS_DRAFT_ONLY, user_query=PERSONNEL_QUERY
    )
    meta = resolve_hermes_reply_source(
        structured_gate_applied=False,
        keep_hermes_final=True,
        hermes_salvaged=True,
        reply=PROCESS_DRAFT_ONLY,
        user_query=PERSONNEL_QUERY,
    )
    assert meta["reply_source"] != "hermes"
    assert meta["reply_source"] in ("hermes_process_draft", "hermes_incomplete")


def test_resolve_hermes_reply_source_non_user_facing_body_not_hermes():
    """有正文但非 user-facing 时不得因 `or body` 标成 hermes。"""
    from backend.services.agent_kb_supplemental import resolve_hermes_reply_source

    sticky = (
        "## 人员结构对照（过程粘贴）\n"
        "next_action=verify_gap_then_write_final\n"
        "核证补缺计划：继续调用 orientg_kb_ask。\n"
    )
    meta = resolve_hermes_reply_source(reply=sticky, user_query=PERSONNEL_QUERY)
    assert meta["reply_source"] != "hermes"
    assert meta["reply_source"] in ("hermes_process_draft", "hermes_incomplete")


def test_pick_hermes_error_fallback_rejects_process_draft_salvage():
    """kb_ask_loop / stall 后不得把过程稿 salvage 成成功终稿。"""
    from backend.services.agent_kb_supplemental import pick_hermes_error_fallback_reply
    from backend.services.hermes_stream_sanitize import HermesDraftTraceAccumulator

    acc = HermesDraftTraceAccumulator()
    acc.push(PROCESS_DRAFT_ONLY)
    reply, mode = pick_hermes_error_fallback_reply(
        draft_acc=acc,
        synth_reply="",
        prefetch_result={"ok": True, "citations": [{"doc_id": "d1"}]},
        user_query=PERSONNEL_QUERY,
    )
    assert mode != "hermes_salvaged"
    assert "Let me first" not in reply
    assert "核证补缺" not in reply


def test_resolve_hermes_reply_source_gate_flag_does_not_override_keep_hermes():
    """门禁曾评估但终稿仍为 Hermes 正文时，不得标 orientg_structured_gate。"""
    from backend.services.agent_kb_supplemental import resolve_hermes_reply_source

    hermes_body = (
        "## 销售费用对比\n"
        "| 分项 | YYCQ | 可比公司A |\n| 广告 | 12000 | 8000 |\n"
        "### 分析\n广告投放差异是主因；口径以年报附注为准。\n"
    )
    meta = resolve_hermes_reply_source(
        structured_gate_applied=True,
        keep_hermes_final=True,
        reply=hermes_body,
    )
    assert meta["reply_source"] == "hermes"
    assert meta.get("structured_gate_applied") is False


def test_hermes_answer_requirements_ban_code_parse_after_mcp():
    from backend.services.agent_hermes_tier_policy import hermes_answer_requirements

    req = hermes_answer_requirements(tier="full", user_query=FINANCE_QUERY)
    assert "execute_code" in req or "terminal" in req
    assert "直接" in req or "成稿" in req


def test_personnel_requirements_still_ban_code_but_not_personnel_only_authorship():
    """人员样例策略可禁 code，但文案不得声称『仅人员 Hermes 主写』。"""
    from backend.services.agent_hermes_tier_policy import hermes_answer_requirements

    req = hermes_answer_requirements(tier="full", user_query=PERSONNEL_QUERY)
    assert "execute_code" in req or "terminal" in req
    assert "仅人员" not in req
    assert "人员结构对照" in req


def test_kb_ask_hint_urges_read_mcp_text_not_code():
    from backend.services.hermes_kb_mcp_bridge import kb_ask_tool_invocation_hint

    hint = kb_ask_tool_invocation_hint(
        session_key="sk",
        user_query=FINANCE_QUERY,
        native_mode=True,
    )
    instr = str(hint.get("instruction") or "")
    assert "直接" in instr or "成稿" in instr
    assert "execute_code" in instr
    assert "读" in instr or "文本" in instr or "节选" in instr


def test_deep_native_skips_supplemental_globally(monkeypatch):
    """深度 native：任意问答跳过网关补检索顶替（非仅人员）。"""
    from backend.config import settings
    from backend.services.agent_kb_router import AgentRoute
    from backend.services.agent_kb_supplemental import needs_hermes_supplemental

    monkeypatch.setattr(settings, "hermes_native_mcp_reply", True)
    monkeypatch.setattr(settings, "hermes_native_skip_supplemental", True)
    prefetch = {
        "ok": True,
        "citations": [{"doc_id": "d1"}],
        "evidence_pack": {"task_type": "compare", "gaps": ["x"]},
    }
    assert not needs_hermes_supplemental(
        agent_route=AgentRoute.hermes_full,
        prefetch_result=prefetch,
        hermes_kb_ask_count=0,
        hermes_reply="过程稿很短",
        user_query=FINANCE_QUERY,
    )


def test_qualified_hermes_final_skips_no_mcp_supplemental_even_kb0(monkeypatch):
    """手测回归：kb=0 但已有合格 Hermes 终稿时，禁止「未调 MCP 补检索」毁流。

    与假 MCP 优先重试同类保险丝；预检索/pack 成稿或 MCP 计数假 0 均适用（全局，非人员作弊）。
    """
    from backend.config import settings
    from backend.services.agent_kb_router import AgentRoute
    from backend.services.agent_kb_supplemental import needs_hermes_supplemental
    from backend.services.hermes_response_analysis import hermes_reply_is_user_facing_final

    monkeypatch.setattr(settings, "hermes_native_mcp_reply", True)
    monkeypatch.setattr(settings, "hermes_native_skip_supplemental", True)
    # 英文过程开场 + 双侧对照表（用户面合格，但 looks_like_planning 易误杀）
    draft = (
        "Let me first retrieve the personnel structure for both companies via orientg_kb_ask.\n"
        "## 人员结构对照\n"
        "| 职能 | 可比公司A | YYCQ |\n"
        "| --- | --- | --- |\n"
        "| 研发 | 1,378 | 70 |\n"
        "| 销售 | 946 | 证据未覆盖 |\n"
        "| 运营 | 242 | 61 |\n"
        "### 对比分析\n"
        "规模差异显著；口径：年报 vs excel。\n"
    )
    assert hermes_reply_is_user_facing_final(draft, user_query=PERSONNEL_QUERY)
    prefetch = {
        "ok": True,
        "citations": [{"doc_id": "d1"}],
        "evidence_pack": {"task_type": "compare", "gaps": ["x"]},
    }
    assert not needs_hermes_supplemental(
        agent_route=AgentRoute.hermes_full,
        prefetch_result=prefetch,
        hermes_kb_ask_count=0,
        hermes_reply=draft,
        user_query=PERSONNEL_QUERY,
    )

    # 财务对照同样：合格终稿 + kb=0 → 禁补检索
    finance_draft = (
        "## 销售费用对比分析报告\n"
        "| 项目 | YYCQ | 可比公司A |\n"
        "| --- | --- | --- |\n"
        "| 销售费用合计 | 13,722,360.23 | 25,081,092.51 |\n"
        "### 分析\n广告与职工薪酬为主要差异，口径以年报附注为准。\n"
    )
    assert hermes_reply_is_user_facing_final(finance_draft, user_query=FINANCE_QUERY)
    assert not needs_hermes_supplemental(
        agent_route=AgentRoute.hermes_full,
        prefetch_result=prefetch,
        hermes_kb_ask_count=0,
        hermes_reply=finance_draft,
        user_query=FINANCE_QUERY,
    )


def test_substantive_process_draft_kb0_skips_no_mcp_supplemental(monkeypatch):
    """手测回归：实质过程稿 + kb=0 → 禁「未调 MCP 补检索×N」毁流。

    与跳过 MCP 优先重试对齐：已有可 salvage 实质稿时走成稿续跑/短路径，
    不得因 looks_like_planning / 非 user-facing 再开网关补检索链。
    全局（人员+财务），禁止人员专用硬放行。
    """
    from backend.config import settings
    from backend.services.agent_kb_router import AgentRoute
    from backend.services.agent_kb_supplemental import needs_hermes_supplemental
    from backend.services.hermes_response_analysis import (
        hermes_reply_has_substantive_draft,
        hermes_reply_is_user_facing_final,
    )
    from backend.services.hermes_stream_sanitize import looks_like_planning

    monkeypatch.setattr(settings, "hermes_native_mcp_reply", True)
    monkeypatch.setattr(settings, "hermes_native_skip_supplemental", True)
    prefetch = {
        "ok": True,
        "citations": [{"doc_id": "d1"}],
        "evidence_pack": {"task_type": "compare", "gaps": ["x"]},
    }

    # 人员：核证补缺过程稿（evidence_sufficient=false），含证据数字
    personnel_process = (
        "首轮取证完成。可比公司A研发人员1378人，YYCQ70人。"
        "正在做核证补缺计划后撰写终稿。evidence_sufficient=false"
    )
    assert hermes_reply_has_substantive_draft(
        personnel_process, user_query=PERSONNEL_QUERY
    )
    assert not hermes_reply_is_user_facing_final(
        personnel_process, user_query=PERSONNEL_QUERY
    )
    assert looks_like_planning(personnel_process)
    assert not needs_hermes_supplemental(
        agent_route=AgentRoute.hermes_full,
        prefetch_result=prefetch,
        hermes_kb_ask_count=0,
        hermes_reply=personnel_process,
        user_query=PERSONNEL_QUERY,
    )

    # 财务：同样实质过程稿 + kb=0 → 禁补检索（非人员作弊；勿带对照表以免误判终稿）
    finance_process = (
        "已核对预检索节选。YYCQ销售费用合计13722360.23元，可比公司A约25081092.51元。"
        "evidence_sufficient=false，核证补缺计划 verification_queries 完成后撰写终稿。"
    )
    assert hermes_reply_has_substantive_draft(finance_process, user_query=FINANCE_QUERY)
    assert not hermes_reply_is_user_facing_final(
        finance_process, user_query=FINANCE_QUERY
    )
    assert not needs_hermes_supplemental(
        agent_route=AgentRoute.hermes_full,
        prefetch_result=prefetch,
        hermes_kb_ask_count=0,
        hermes_reply=finance_process,
        user_query=FINANCE_QUERY,
    )


BILATERAL_PERSONNEL_DRAFT = (
    "### 人员结构对照\n"
    "职能分类\t可比公司A\tYYCQ\n"
    "研发人员\t1,378人\t70人\n"
    "销售人员\t946人\t证据未覆盖\n"
    "运营人员\t242人\t61人\n"
    "### 对比分析\n"
    "规模差异显著：可比公司A研发 1,378 人，YYCQ 70 人；"
    "销售侧YYCQ证据未覆盖，运营 242 vs 61。\n"
    "### 口径说明\n"
    "可比公司A来自年报专业构成/研发人员情况；YYCQ来自 excel 职能分项。\n"
)

DUAL_DRAFT_WITH_PLANNING = (
    "Let me first retrieve personnel data via orientg_kb_ask.\n"
    "evidence_sufficient=false\n核证补缺计划：verification_queries 若干。\n\n"
    + BILATERAL_PERSONNEL_DRAFT
)


def test_bilateral_compare_table_is_user_facing_not_incomplete():
    """已有双侧人数对照表的 Hermes draft 不得标未成稿 / 不得换成证据不足套话。

    用通用终稿质量标准（非人员专用放行）。
    """
    from backend.services.agent_kb_supplemental import (
        PERSONNEL_EVIDENCE_INSUFFICIENT_REPLY,
        prefer_user_facing_hermes_final,
        resolve_hermes_reply_source,
    )
    from backend.services.hermes_response_analysis import hermes_reply_is_user_facing_final

    assert hermes_reply_is_user_facing_final(
        BILATERAL_PERSONNEL_DRAFT, user_query=PERSONNEL_QUERY
    )
    # 夹杂英文过程句：须先剥离再判，不得整篇误杀
    kept = prefer_user_facing_hermes_final(
        DUAL_DRAFT_WITH_PLANNING,
        alt_draft="",
        user_query=PERSONNEL_QUERY,
    )
    assert hermes_reply_is_user_facing_final(kept, user_query=PERSONNEL_QUERY)
    assert "人员结构对照" in kept
    assert "1,378" in kept or "1378" in kept
    assert PERSONNEL_EVIDENCE_INSUFFICIENT_REPLY not in kept
    meta = resolve_hermes_reply_source(
        reply=kept,
        user_query=PERSONNEL_QUERY,
        keep_hermes_final=True,
    )
    assert meta["reply_source"] == "hermes"


def test_prefer_user_facing_recovers_draft_when_final_is_insufficient_template():
    """主气泡已被套话顶替时，应从过程稿/draft 恢复合格终稿（全局，非人员特判）。"""
    from backend.services.agent_kb_supplemental import (
        PERSONNEL_EVIDENCE_INSUFFICIENT_REPLY,
        prefer_user_facing_hermes_final,
        resolve_hermes_reply_source,
    )

    recovered = prefer_user_facing_hermes_final(
        PERSONNEL_EVIDENCE_INSUFFICIENT_REPLY,
        alt_draft=DUAL_DRAFT_WITH_PLANNING,
        user_query=PERSONNEL_QUERY,
    )
    assert recovered != PERSONNEL_EVIDENCE_INSUFFICIENT_REPLY
    assert "人员结构对照" in recovered
    meta = resolve_hermes_reply_source(reply=recovered, user_query=PERSONNEL_QUERY)
    assert meta["reply_source"] == "hermes"


def test_non_personnel_deep_compare_same_global_user_facing_gate():
    """非人员深度问答与人员共用同一 user-facing 标准（证明非人员作弊放行）。"""
    from backend.services.hermes_response_analysis import hermes_reply_is_user_facing_final
    from backend.services.agent_kb_supplemental import resolve_hermes_reply_source

    finance = (
        "## 销售费用对比\n"
        "| 分项 | YYCQ | 可比公司A |\n| 广告宣传费 | 1,200.00 | 8,000.50 |\n"
        "### 分析\n广告投放差异是主因；口径以年报附注为准。\n"
    )
    assert hermes_reply_is_user_facing_final(finance, user_query=FINANCE_QUERY)
    meta = resolve_hermes_reply_source(reply=finance, user_query=FINANCE_QUERY)
    assert meta["reply_source"] == "hermes"


def test_tier2_recovery_done_always_has_reply_source(monkeypatch):
    """Hermes stall recovery 的 done 必须带 reply_source（禁缺省漏检）。"""
    from unittest.mock import patch

    from backend.config import settings
    from backend.services.agent_kb_router import AgentRoute
    from backend.services.agent_kb_supplemental import iter_tier2_hermes_error_recovery_events
    from backend.services.hermes_stream_sanitize import HermesDraftTraceAccumulator

    monkeypatch.setattr(settings, "hermes_native_mcp_reply", True)
    monkeypatch.setattr(settings, "hermes_native_skip_supplemental", True)
    acc = HermesDraftTraceAccumulator()
    acc.push(
        "## 销售费用对比\n| 分项 | YYCQ | 可比公司A |\n| 广告 | 12000 | 8000 |\n"
        "### 分析\n广告投放差异为主因，口径以年报附注为准。\n"
    )
    prefetch = {
        "ok": True,
        "citations": [{"doc_id": "d1"}],
        "evidence_pack": {"task_type": "compare", "coverage_score": 0.9},
        "reply": "",
    }
    with (
        patch(
            "backend.services.agent_kb_supplemental.run_supplemental_kb_asks",
            return_value=(prefetch, []),
        ),
        patch(
            "backend.services.agent_kb_prefetch.synthesize_kb_reply",
            return_value={"reply": "本地顶替稿", "citations": [], "synthesis": "local"},
        ),
    ):
        evts = list(
            iter_tier2_hermes_error_recovery_events(
                user_token="tok",
                tenant_id="tenant1",
                user_query=FINANCE_QUERY,
                prefetch_result=prefetch,
                prefetch_tool_calls=[],
                kb_scope={"selected_folder_ids": ["f1"]},
                attached_doc_ids=None,
                fixtures={"tenant_id": "tenant1"},
                agent_route=AgentRoute.hermes_full,
                enabled_skills=None,
                model=None,
                hermes_draft_acc=acc,
                error_code="hermes_stall",
            )
        )
    done = [e for e in evts if e.get("type") == "done"][-1]
    assert done.get("reply_source") == "hermes"
    assert "本地顶替" not in str(done.get("reply") or "")
    assert "广告" in str(done.get("reply") or "")
