"""竞品财报 Hermes 探针问句：设计问题 → 观察 Hermes 回应 → 驱动 MCP 优化。

用法见 backend/scripts/hermes_response_probe_runner.py
规制：specs/plans/1.2.3.d-hermes-native-mcp-tdd.md §8
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ProbeTier = Literal["fast", "standard", "deep"]


@dataclass(frozen=True)
class HermesResponseProbe:
    probe_id: str
    query: str
    tier: ProbeTier
    category: str
    intent: str
    failure_modes: tuple[str, ...] = ()
    mcp_optimization: str = ""
    accept_tags: tuple[str, ...] = ()
    reject_tags: tuple[str, ...] = (
        "kb_empty_hallucination",
        "listed_company_denial",
        "permission_denied",
        "english_planning",
    )


# 竞品财报25 · finance_test · folder f_6f3638e4513f492c9610ddb5dda77c20
HERMES_RESPONSE_PROBES: tuple[HermesResponseProbe, ...] = (
    HermesResponseProbe(
        probe_id="P1",
        query="对比分析YYCQ和可比公司A25年的人员结构",
        tier="deep",
        category="personnel_compare",
        intent="双主体人员横比；Hermes 应 1–2 次 MCP 后直接中文终稿",
        failure_modes=(
            "kb_empty_hallucination",
            "listed_company_denial",
            "hermes_kb_ask_loop",
            "gateway_supplemental_over_2",
        ),
        mcp_optimization="agent_payload.evidence_sufficient + 人员结构对照 contract + entity_hints",
        accept_tags=("personnel_structure_table",),
    ),
    HermesResponseProbe(
        probe_id="P2",
        query="可比公司A2025研发人员数量及占比",
        tier="standard",
        category="personnel_single",
        intent="单主体年报专节；MCP 一次应足",
        failure_modes=("kb_empty_hallucination", "english_planning"),
        mcp_optimization="单主体 metrics.rd_headcount + rd_share_pct",
    ),
    HermesResponseProbe(
        probe_id="P3",
        query="YYCQ2025员工专业构成",
        tier="fast",
        category="personnel_single",
        intent="Excel 1.1信息-人员切块",
        failure_modes=("kb_empty_hallucination", "listed_company_denial"),
        mcp_optimization="entity_hints: YYCQ=KB 内 excel 主体，非 A 股检索名",
    ),
    HermesResponseProbe(
        probe_id="F1",
        query="对比YYCQ与可比公司A2025年销售费用率",
        tier="deep",
        category="finance_compare",
        intent="财务指标横比",
        failure_modes=("kb_empty_hallucination", "english_planning"),
        mcp_optimization="finance_compare output_contract + 核心指标对照",
    ),
    HermesResponseProbe(
        probe_id="H1",
        query="对比YYCQ和可比公司A2025年销售与运营人员规模",
        tier="standard",
        category="personnel_compare",
        intent="职能子集横比",
        failure_modes=("kb_empty_hallucination",),
        mcp_optimization="suggested_queries 含销售/运营专节",
    ),
    HermesResponseProbe(
        probe_id="H2",
        query="Compare employee structure of YYCQ vs 37 Interactive 2025",
        tier="deep",
        category="adversarial",
        intent="英文问句；MCP 应仍返回中文 agent_payload",
        failure_modes=("english_planning",),
        mcp_optimization="output_contract.language=zh-CN + 中文 query 建议",
        reject_tags=("english_planning", "kb_empty_hallucination"),
    ),
)


def probe_by_id(probe_id: str) -> HermesResponseProbe | None:
    pid = (probe_id or "").strip().upper()
    for p in HERMES_RESPONSE_PROBES:
        if p.probe_id == pid:
            return p
    return None
