"""Hermes 回应探针：分类器 + 探针目录单元测试。"""

from __future__ import annotations

from backend.services.hermes_response_analysis import (
    classify_hermes_response,
    hermes_personnel_compare_quality_score,
    hermes_reply_has_kb_empty_hallucination,
    hermes_reply_has_listed_company_denial,
)
from backend.services.hermes_response_probes import (
    HERMES_RESPONSE_PROBES,
    probe_by_id,
)

PERSONNEL_Q = "对比分析YYCQ和可比公司A25年的人员结构"

GOOD_DRAFT = """
YYCQ vs 可比公司A · 2025 人员结构对比
### 人员结构对照
| 职能 | 可比公司A | YYCQ |
| 研发 | 1378 人 | 70 人 |
| 销售 | 946 人 | 证据未覆盖 |
| 运营 | 242 人 | 61 人 |
### 对比分析
两家口径不同，研发维度可比。
"""

BAD_EVT = """
知识库当前没有任何可用文档，MCP 检索全部被拒绝。
经核实，A股市场中没有名为「YYCQ」的上市公司。请确认你想对比的是哪家公司？
是否需要我先上传相关年报？
"""

PERMISSION_DENIED_EVT = """
知识库当前权限受限，无法检索YYCQ与可比公司A的人员结构数据。
我将尝试通过 web 搜索补充公开信息。
"""


def test_classify_kb_empty_hallucination():
    c = classify_hermes_response(BAD_EVT, user_query=PERSONNEL_Q)
    assert "kb_empty_hallucination" in c["tags"]
    assert "listed_company_denial" in c["tags"]
    assert c["acceptable_personnel_final"] is False


def test_classify_kb_permission_denied_hallucination():
    """手测回归：「知识库当前权限受限，无法检索」须判为 KB 空转/拒答话术。"""
    c = classify_hermes_response(PERMISSION_DENIED_EVT, user_query=PERSONNEL_Q)
    assert "permission_denied" in c["tags"] or "kb_empty_hallucination" in c["tags"]
    assert c["acceptable_personnel_final"] is False
    score = hermes_personnel_compare_quality_score(PERMISSION_DENIED_EVT, user_query=PERSONNEL_Q)
    assert score < 30


def test_classify_good_personnel_draft():
    c = classify_hermes_response(GOOD_DRAFT, user_query=PERSONNEL_Q)
    assert "personnel_structure_table" in c["tags"]
    assert "kb_empty_hallucination" not in c["tags"]
    assert c["acceptable_personnel_final"] is True


def test_classify_let_me_first_process_draft_not_final():
    """手测假绿：Let me first retrieve… + 核证补缺计划 ≠ 可验收终稿。"""
    from backend.services.hermes_response_analysis import (
        hermes_reply_has_substantive_draft,
        hermes_reply_is_user_facing_final,
    )

    draft = (
        "Let me first retrieve personnel data via orientg_kb_ask.\n"
        "evidence_sufficient=false\n核证补缺计划：verification_queries 若干。\n"
        "next_action=verify_gap_then_write_final\n"
    )
    c = classify_hermes_response(draft, user_query=PERSONNEL_Q)
    assert "english_planning" in c["tags"] or "process_draft" in c["tags"]
    assert c["acceptable_personnel_final"] is False
    assert not hermes_reply_is_user_facing_final(draft, user_query=PERSONNEL_Q)
    # 纯英文 planning 无数字 → 不算实质过程稿（仍允许真·零 MCP 重试）
    assert not hermes_reply_has_substantive_draft(draft, user_query=PERSONNEL_Q)


def test_substantive_process_draft_with_evidence_numbers():
    """含证据数字的核证过程稿：非 user-facing，但是实质稿（禁假重试）。"""
    from backend.services.hermes_response_analysis import (
        hermes_reply_has_substantive_draft,
        hermes_reply_is_user_facing_final,
    )

    draft = (
        "首轮取证完成。可比公司A研发人员1378人，YYCQ70人。"
        "正在做核证补缺计划后撰写终稿。"
    )
    assert not hermes_reply_is_user_facing_final(draft, user_query=PERSONNEL_Q)
    assert hermes_reply_has_substantive_draft(draft, user_query=PERSONNEL_Q)


def test_quality_score_prefers_draft_over_hallucination_evt():
    draft_score = hermes_personnel_compare_quality_score(GOOD_DRAFT, user_query=PERSONNEL_Q)
    evt_score = hermes_personnel_compare_quality_score(BAD_EVT, user_query=PERSONNEL_Q)
    assert draft_score >= 50
    assert evt_score < 30
    assert draft_score > evt_score


SPECULATIVE_LONG = """
### 人员结构对照
| 职能 | 可比公司A | YYCQ |
| 研发 | 1378 人 | 70 人 |
### 对比分析
根据推算，可比公司A销售人员约1200人，可推断其销售规模远超YYCQ。
YYCQ职能结构可推断为研发驱动型，约70人研发对应较大投入。
*(注：部分分项为模型推断，请勿采信)*
"""


def test_quality_score_penalizes_speculation_and_approx_headcount():
    """宽尺子 C：含推算/推断/约N人的长分析质量分须低于克制对照表。"""
    good = hermes_personnel_compare_quality_score(GOOD_DRAFT, user_query=PERSONNEL_Q)
    bad = hermes_personnel_compare_quality_score(SPECULATIVE_LONG, user_query=PERSONNEL_Q)
    assert good >= 50
    assert bad < good
    assert bad < 50
    c = classify_hermes_response(SPECULATIVE_LONG, user_query=PERSONNEL_Q)
    assert c["acceptable_personnel_final"] is False
    assert "unsupported_speculation" in c["tags"]


def test_classify_rejects_mcp_draft_skeleton_as_final():
    sk = (
        "## 成稿骨架（请原样采用下列数字写入终稿；禁止改写为员工总数倍数对照）\n"
        "### 人员结构对照\n| 职能 | 可比公司A | YYCQ |\n"
        "| 研发 | 1378 人 | 70 人 |\n| 销售 | 946 人 | 证据未覆盖 |\n"
        "| 运营 | 242 人 | 61 人 |\n### 对比分析\n结构差异。\n"
    )
    c = classify_hermes_response(sk, user_query=PERSONNEL_Q)
    assert "mcp_draft_skeleton" in c["tags"]
    assert c["acceptable_personnel_final"] is False


def test_resolve_prefers_clean_table_over_speculation_analysis():
    """过程区合规对照表不得被后写含推算的长分析劣币驱逐。"""
    from backend.services.hermes_stream_sanitize import (
        HermesDraftTraceAccumulator,
        resolve_hermes_effective_reply,
    )

    acc = HermesDraftTraceAccumulator()
    acc.push(GOOD_DRAFT)
    out = resolve_hermes_effective_reply(
        evt_reply=SPECULATIVE_LONG,
        draft_acc=acc,
        user_query=PERSONNEL_Q,
    )
    assert "人员结构对照" in out
    assert "推算" not in out
    assert "推断" not in out
    assert "约1200" not in out
    assert "请勿采信" not in out


def test_resolve_effective_reply_quality_pick():
    from backend.services.hermes_stream_sanitize import (
        HermesDraftTraceAccumulator,
        resolve_hermes_effective_reply,
    )

    acc = HermesDraftTraceAccumulator()
    acc.push(GOOD_DRAFT)
    out = resolve_hermes_effective_reply(
        evt_reply=BAD_EVT,
        draft_acc=acc,
        user_query=PERSONNEL_Q,
    )
    assert "人员结构对照" in out
    assert "知识库当前没有任何可用文档" not in out


def test_probe_catalog_covers_competitor_finance():
    ids = {p.probe_id for p in HERMES_RESPONSE_PROBES}
    assert {"P1", "P2", "P3", "F1", "H1", "H2"} <= ids
    p1 = probe_by_id("P1")
    assert p1 is not None
    assert p1.tier == "deep"
    assert "kb_empty_hallucination" in p1.failure_modes


def test_native_payload_includes_entity_hints():
    from backend.services.kb_ask_mcp_agent_native import build_agent_payload

    payload = build_agent_payload(
        query=PERSONNEL_Q,
        excerpts=[
            {"entity": "可比公司A", "doc_id": "ud_a", "excerpt": "研发 1378 946 242"},
            {"entity": "YYCQ", "doc_id": "ud_b", "excerpt": "研发 70 运营 61"},
        ],
        citations=[{"doc_id": "ud_a"}, {"doc_id": "ud_b"}],
    )
    assert payload.get("entity_hints")
    assert payload.get("kb_status", {}).get("empty") is False
    assert "YYCQ" in str(payload.get("entity_hints"))


def test_entity_hints_map_user_aliases(monkeypatch):
    from backend.services import kb_compare_entities as ce
    from backend.services.kb_ask_mcp_agent_native import build_agent_payload

    monkeypatch.setenv("KB_COMPARE_ENTITY_PRIMARY_ALIASES", "YYCQ")
    monkeypatch.setenv("KB_COMPARE_ENTITY_PEER_ALIASES", "可比公司A")
    monkeypatch.setenv("KB_COMPARE_ENTITY_EXTRA_MARKERS", "YYCQ,可比公司A")
    ce.clear_compare_entity_cache()
    try:
        payload = build_agent_payload(
            query="对比分析YYCQ和可比公司A25年的人员结构",
            excerpts=[
                {"entity": "可比公司A", "doc_id": "ud_a", "excerpt": "研发 1378 946 242"},
                {"entity": "YYCQ", "doc_id": "ud_b", "excerpt": "研发 70 运营 61"},
            ],
            citations=[{"doc_id": "ud_a"}, {"doc_id": "ud_b"}],
        )
        blob = str(payload.get("entity_hints"))
        assert "即用户所称可比公司A" in blob or "可比公司A" in blob
        assert "即用户所称YYCQ" in blob or "YYCQ" in blob
        assert "禁止把" in blob or "展示" in blob
    finally:
        ce.clear_compare_entity_cache()


def test_native_sufficient_accepts_structured_short_draft():
    from backend.services.kb_ask_mcp_agent_native import hermes_native_personnel_reply_sufficient
    from backend.tests.test_hermes_response_probes import GOOD_DRAFT, PERSONNEL_Q

    assert hermes_native_personnel_reply_sufficient(
        GOOD_DRAFT,
        user_query=PERSONNEL_Q,
        hermes_kb_ask_count=1,
    )


def test_needs_hermes_supplemental_false_when_native_sufficient(monkeypatch):
    from backend.config import settings
    from backend.services.agent_kb_router import AgentRoute
    from backend.services.agent_kb_supplemental import needs_hermes_supplemental
    from backend.tests.test_hermes_response_probes import GOOD_DRAFT, PERSONNEL_Q

    monkeypatch.setattr(settings, "hermes_native_mcp_reply", True)
    monkeypatch.setattr(settings, "hermes_native_skip_supplemental", True)
    prefetch = {
        "ok": True,
        "evidence_pack": {"task_type": "compare", "retrieval_queries": [PERSONNEL_Q]},
        "citations": [{"doc_id": "d1"}],
    }
    assert not needs_hermes_supplemental(
        agent_route=AgentRoute.hermes_full,
        prefetch_result=prefetch,
        hermes_kb_ask_count=1,
        hermes_reply=GOOD_DRAFT,
        user_query=PERSONNEL_Q,
    )


def test_needs_hermes_supplemental_false_native_skip_even_if_draft_weak(monkeypatch):
    """native skip：人员横比且 Hermes 已 kb_ask≥1 时一律跳过补检索（弱稿交 gate 保险丝）。"""
    from backend.config import settings
    from backend.services.agent_kb_router import AgentRoute
    from backend.services.agent_kb_supplemental import needs_hermes_supplemental

    monkeypatch.setattr(settings, "hermes_native_mcp_reply", True)
    monkeypatch.setattr(settings, "hermes_native_skip_supplemental", True)
    prefetch = {
        "ok": True,
        "evidence_pack": {"task_type": "compare", "retrieval_queries": [PERSONNEL_Q]},
        "citations": [{"doc_id": "d1"}],
    }
    weak = "I'll search more. 可比公司A 3138 YYCQ 139。"
    assert not needs_hermes_supplemental(
        agent_route=AgentRoute.hermes_full,
        prefetch_result=prefetch,
        hermes_kb_ask_count=2,
        hermes_reply=weak,
        user_query=PERSONNEL_Q,
    )


def test_supplemental_max_reduced_when_native_and_hermes_mcp():
    from backend.config import settings
    from backend.services.agent_kb_router import AgentRoute
    from backend.services.agent_kb_supplemental import supplemental_max_queries_for_route

    q = PERSONNEL_Q
    assert supplemental_max_queries_for_route(AgentRoute.hermes_full, user_query=q) == 8
    if settings.hermes_native_mcp_reply:
        assert (
            supplemental_max_queries_for_route(
                AgentRoute.hermes_full,
                user_query=q,
                hermes_kb_ask_count=1,
            )
            == 2
        )
