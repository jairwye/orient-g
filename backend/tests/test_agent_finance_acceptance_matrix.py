"""
财务智能体验收矩阵（TDD）：利润表 / 资产负债表 / 现金流 / 附注 × 快/标/深。

页面实测清单：docs/finance-agent-acceptance-matrix.md（finance_test + 竞品财报25 + MCP）。
"""
from __future__ import annotations

import os
import re

import pytest

from backend.services.agent_kb_router import AgentRoute, resolve_agent_route, route_to_agent_tier
from backend.services.evidence_reply_align import reply_has_derived_breakdown_amounts
from backend.services.hermes_stream_sanitize import finalize_agent_reply, reply_has_unsupported_estimates
from backend.services.kb_retrieval_plan import infer_task_type, plan_retrieval_queries

pytestmark = pytest.mark.agent_finance_matrix

MATRIX_ROWS: list[tuple[str, str, str]] = [
    ("pnl", "研发费用", "出一份华清25、24两年研发费用明细的对比分析报告"),
    ("pnl", "销售费用", "出一份华清25、24两年销售费用明细的对比分析报告"),
    ("pnl", "管理费用", "出一份华清25、24两年管理费用明细的对比分析报告"),
    ("pnl", "营业收入", "华清2025年与2024年营业收入对比及变动说明"),
    ("pnl", "净利润", "华清2025年与2024年净利润对比分析"),
    ("bs", "货币资金", "华清2025年末与2024年末货币资金对比"),
    ("bs", "应收账款", "华清2025年末与2024年末应收账款余额对比"),
    ("bs", "存货", "华清2025年末与2024年末存货对比"),
    ("bs", "固定资产", "华清2025年末与2024年末固定资产账面价值对比"),
    ("cf", "经营活动现金流", "华清2025年与2024年经营活动产生的现金流量净额对比"),
    ("cf", "投资活动现金流", "华清2025年与2024年投资活动现金流量对比"),
    ("cf", "筹资活动现金流", "华清2025年与2024年筹资活动现金流量对比"),
    ("note", "附注-费用", "华清财报附注中2025与2024年三项期间费用合计对比"),
    ("note", "附注-研发", "根据附注说明华清两年研发支出构成变化"),
]

TIER_CASES = [
    ("fast", "fast", 0),
    ("standard", "standard", 1),
    ("deep", "deep", 2),
]


@pytest.mark.parametrize("category,subject,query", MATRIX_ROWS)
@pytest.mark.parametrize("mode_name,agent_mode,expected_tier", TIER_CASES)
def test_matrix_route_tier(
    category: str,
    subject: str,
    query: str,
    mode_name: str,
    agent_mode: str,
    expected_tier: int,
):
    route = resolve_agent_route(
        user_query=query,
        agent_mode=agent_mode,
        allow_kb_write=False,
        has_kb_scope=True,
        prefetch_result={"evidence_pack": {"chunks": [{"text": "x"}]}, "citations": [{}]},
        hermes_configured=True,
    )
    assert route_to_agent_tier(route) == expected_tier
    if mode_name == "standard":
        assert route == AgentRoute.hermes_lite
    if mode_name == "deep":
        assert route == AgentRoute.hermes_full
    if mode_name == "fast":
        assert route == AgentRoute.fast


@pytest.mark.parametrize("category,subject,query", MATRIX_ROWS)
def test_matrix_retrieval_plan_has_query(category: str, subject: str, query: str):
    tt = infer_task_type(query)
    plan = plan_retrieval_queries(query, tt, entity="华清", max_queries=6)
    assert plan[0] == query
    assert len(plan) >= 1


@pytest.mark.parametrize("category,subject,query", MATRIX_ROWS[:8])
def test_matrix_finalize_no_glued_table(category: str, subject: str, query: str):
    raw = (
        f"结论：2025年{subject}有可比数据。|项目 |2025年 |2024年 |差额 |\n"
        "|---|---|---|---|\n"
        f"|合计 |1.00 |2.00 | -1.00 |说明：附注口径一致。"
    )
    out = finalize_agent_reply(raw, user_query=query)
    assert "。|项目" not in out and "数据。|项目" not in out
    assert "\n\n|" in out
    assert "\n\n### 说明" in out


def test_matrix_blocks_derived_breakdown():
    reply = "职工薪酬约 7086 万元；反推：122568-51705=70863"
    assert reply_has_derived_breakdown_amounts(reply) or reply_has_unsupported_estimates(reply)


@pytest.mark.skipif(
    os.environ.get("ORIENTG_LIVE_FINANCE_MCP") != "1",
    reason="本机全栈；ORIENTG_LIVE_FINANCE_MCP=1 跑 MCP+pack 烟雾（串行）",
)
@pytest.mark.parametrize("category,subject,query", MATRIX_ROWS[:3])
def test_live_finance_mcp_pack_smoke(category: str, subject: str, query: str):
    """finance_test + 竞品财报25：retrieve pack + orientg_kb_ask（非完整 Hermes 流）。"""
    from fastapi.testclient import TestClient

    from backend.main import app
    from backend.routers.settings import DEPARTMENT_FINANCE
    from backend.services.dev_users import ensure_department_test_user
    from backend.services.kb_retrieve_pack import retrieve_kb_evidence_pack
    from backend.services.kb_scope_resolve import resolve_kb_scope_for_ask
    from backend.services.knowledge_acl import load_fixtures
    from backend.services import orientg_mcp_tools as mcp_tools
    from backend.tests.test_acl_folder_shared_docs import FOLDER_JINGPIN_CAIBAO_25

    client = TestClient(app)
    ensure_department_test_user(
        "finance_test",
        password="FinanceTest!2026",
        department=DEPARTMENT_FINANCE,
    )
    r = client.post(
        "/api/auth/login",
        json={"username": "finance_test", "password": "FinanceTest!2026"},
    )
    assert r.status_code == 200
    token = r.json()["token"]
    scope = {"selected_folder_ids": [FOLDER_JINGPIN_CAIBAO_25]}
    fixtures = load_fixtures()
    resolved = resolve_kb_scope_for_ask("tenant1", scope)
    pack_res, _ = retrieve_kb_evidence_pack(
        token,
        query,
        scope,
        fixtures=fixtures,
        resolved_scope=resolved,
        multi_query=True,
    )
    assert pack_res.get("ok"), pack_res
    subq = subject.replace("费用", "")[:8] or "华清"
    mcp_out = mcp_tools.orientg_kb_ask(
        token,
        f"华清 {subq} 2024 2025",
        attached_doc_ids=list(resolved.get("attached_doc_ids") or [])[:200],
        limit_to_attached=bool(resolved.get("limit_to_attached")),
    )
    assert mcp_out.get("ok") is True, mcp_out
    assert len(mcp_out.get("citations") or []) >= 2
