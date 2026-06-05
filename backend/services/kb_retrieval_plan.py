"""任务意图与多 query 检索计划（规则驱动）。"""

from __future__ import annotations

import re
from enum import Enum

from backend.services.knowledge_pipeline import _entity_terms_from_query


class TaskType(str, Enum):
    fact = "fact"
    compare = "compare"
    breakdown = "breakdown"
    process = "process"
    general = "general"


_BREAKDOWN_PAT = re.compile(r"成本|费用|明细|拆解|分解|归因|下降|结构", re.I)
_COMPARE_PAT = re.compile(r"对比|比较|两年|同比|24|25|2024|2025|损益", re.I)
_PROCESS_PAT = re.compile(r"流程|制度|审批|规定|办法|如何办理", re.I)
_FACT_PAT = re.compile(r"多少|是什么|什么意思|如何理解|营收|收入", re.I)
_REASON_PAT = re.compile(
    r"分析报告|原因|归因|为何|为什么|怎么回事|变动说明|情况说明",
    re.I,
)
_REASON_HOW_PAT = re.compile(r"(怎么|如何|为何).*(下降|上升|变动|减少|增加|变化)", re.I)

# 期间费用/成本科目（问句驱动，非写死单一科目）
PERIOD_FEE_SUBJECTS: tuple[str, ...] = (
    "销售费用",
    "管理费用",
    "研发费用",
    "财务费用",
    "营业成本",
)

# 报表科目词表（行业通用词汇，非某公司/某锚点金额）
_BALANCE_SHEET_ITEM_RE = re.compile(
    r"(货币资金|应收账款|应收款项|其他应收款|预付款项|存货|合同资产|"
    r"固定资产|在建工程|无形资产|商誉|长期股权投资|短期借款|应付账款|"
    r"资产总计|负债总计|净资产|流动资产|非流动资产)",
)
_PNL_LINE_ITEM_RE = re.compile(
    r"(营业收入|营业成本|营业利润|净利润|归属于母公司(?:所有者)?(?:股东)?的净利润|"
    r"总资产|总负债|每股收益)",
)
_CF_ACTIVITY_RE = re.compile(r"(经营|投资|筹资)活动")


def _cf_subject_for_activity(activity: str) -> str:
    return f"{activity}活动产生的现金流量净额"


def compare_subjects_from_query(user_query: str) -> list[str]:
    """从问句提取对比科目（费用/资产负债/现金流/损益，问句驱动）。"""
    qj = (user_query or "").replace(" ", "")
    out: list[str] = []
    seen: set[str] = set()

    def _add(item: str) -> None:
        s = (item or "").strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)

    for s in fee_subjects_from_query(user_query):
        _add(s)
    for m in _BALANCE_SHEET_ITEM_RE.finditer(qj):
        _add(m.group(1))
    for m in _PNL_LINE_ITEM_RE.finditer(qj):
        _add(m.group(1))
    if "现金流" in qj:
        for m in _CF_ACTIVITY_RE.finditer(qj):
            _add(_cf_subject_for_activity(m.group(1)))
    if "附注" in qj and "费用" in qj and not any("费用" in x for x in out):
        _add("期间费用")
    return out


def bs_subjects_from_query(user_query: str) -> list[str]:
    """资产负债表类科目（compare 子 query 用）。"""
    bs_keys = (
        "货币资金", "应收账款", "应收款项", "存货", "固定资产", "长期股权投资",
        "无形资产", "在建工程", "资产总计", "负债总计",
    )
    return [s for s in compare_subjects_from_query(user_query) if s in bs_keys or s.endswith("资产")]


def cf_subjects_from_query(user_query: str) -> list[str]:
    """现金流量表类科目（compare 子 query 用）。"""
    return [s for s in compare_subjects_from_query(user_query) if "现金流量" in s]


def _plan_bs_compare_subqueries(add, *, prefix: str, subjects: list[str]) -> None:
    for subj in subjects[:3]:
        add(f"{prefix}{subj} 2024 2025 年末")
        add(f"{prefix}合并资产负债表 {subj}")
        add(f"{prefix}{subj} 期末余额")


def _plan_cf_compare_subqueries(add, *, prefix: str, subjects: list[str]) -> None:
    add(f"{prefix}现金流量表 2024 2025")
    for subj in subjects[:2]:
        add(f"{prefix}{subj} 2024 2025")
        add(f"{prefix}合并现金流量表 {subj.replace('现金流量', '')}")


def fee_subjects_from_query(user_query: str) -> list[str]:
    """从问句提取费用/成本科目；未点名时返回空（由 plan 层决定默认子 query）。"""
    qj = (user_query or "").replace(" ", "")
    return [s for s in PERIOD_FEE_SUBJECTS if s in qj]


def _plan_fee_note_subqueries(
    add,
    *,
    prefix: str,
    subjects: list[str],
    wants_reason: bool,
) -> None:
    """breakdown/compare 附注分项子 query（按问句科目，非写死销售费用）。"""
    targets = subjects or ["销售费用", "管理费用"]
    for subj in targets[:3]:
        add(f"{prefix}{subj} 附注")
        add(f"{prefix}## {subj}")
        add(f"{prefix}合并财务报表项目注释 {subj}")
    if wants_reason:
        for subj in targets[:2]:
            add(f"{prefix}{subj} 变动原因")
        add(f"{prefix}项目重大变动原因")
        add(f"{prefix}经营情况讨论 期间费用")


def query_wants_analyst_report(user_query: str) -> bool:
    """问句要求分析师级长报告（深度 Tier 2），非仅明细对比表。"""
    qj = (user_query or "").replace(" ", "")
    if not qj:
        return False
    if re.search(r"分析报告|深度分析|研报", qj):
        return True
    if _COMPARE_PAT.search(qj) and any(x in qj for x in ("报告", "分析")):
        return True
    return False


def query_wants_change_reasons(user_query: str) -> bool:
    """问句需要文字性变动原因/分析（须证据支持，非模型推断）。"""
    qj = (user_query or "").replace(" ", "")
    if not qj:
        return False
    if _REASON_PAT.search(qj):
        return True
    if _REASON_HOW_PAT.search(qj):
        return True
    if _COMPARE_PAT.search(qj) and any(x in qj for x in ("报告", "分析", "说明")):
        return True
    return False


def infer_task_type(user_query: str) -> TaskType:
    q = (user_query or "").strip()
    if not q:
        return TaskType.general
    qj = q.replace(" ", "")
    if _PROCESS_PAT.search(q):
        return TaskType.process
    if _BREAKDOWN_PAT.search(qj):
        return TaskType.breakdown
    if _FACT_PAT.search(qj) and not re.search(r"对比|比较|两年|同比|损益", qj):
        return TaskType.fact
    if _COMPARE_PAT.search(qj):
        return TaskType.compare
    return TaskType.general


def detect_entity(user_query: str) -> str:
    ents = _entity_terms_from_query(user_query)
    for e in ents:
        if e and len(e) >= 2:
            return e
    return ""


def _append_narrative_subqueries(
    add,
    *,
    prefix: str,
    wants_analyst: bool,
) -> None:
    """深度/分析报告：补经营叙事类子 query（A）。"""
    if not wants_analyst:
        return
    add(f"{prefix}经营情况讨论 主营业务 产品")
    add(f"{prefix}管理层讨论与分析 期间费用")
    add(f"{prefix}市场及推广费用 变动 原因")
    add(f"{prefix}营业收入 变动原因 2024 2025")


def plan_retrieval_queries(
    user_query: str,
    task_type: TaskType | str,
    *,
    entity: str | None = None,
    max_queries: int = 5,
    prefetch_tier: str | None = None,
) -> list[str]:
    """首条始终为用户原问；其余为定向子 query。"""
    q = (user_query or "").strip()
    if not q:
        return []
    tt = TaskType(task_type) if isinstance(task_type, str) else task_type
    ent = (entity or "").strip() or detect_entity(q)
    prefix = f"{ent} " if ent else ""
    qj = q.replace(" ", "")
    wants_reason = query_wants_change_reasons(q)
    wants_analyst = query_wants_analyst_report(q) or (prefetch_tier or "").strip().lower() == "full"
    cap = max_queries
    if wants_reason:
        cap = max(cap, 6)
    if wants_analyst:
        cap = max(cap, 8)
    out = [q]

    def _add(s: str) -> None:
        s = (s or "").strip()
        if s and s not in out and len(out) < cap:
            out.append(s)

    fee_subjects = fee_subjects_from_query(q)
    bs_subjects = bs_subjects_from_query(q)
    cf_subjects = cf_subjects_from_query(q)

    if tt == TaskType.breakdown:
        if wants_analyst:
            _append_narrative_subqueries(_add, prefix=prefix, wants_analyst=True)
        _plan_fee_note_subqueries(
            _add,
            prefix=prefix,
            subjects=fee_subjects,
            wants_reason=wants_reason,
        )
        if not wants_reason:
            _add(f"{prefix}营业成本 变动原因")
        _add(f"{prefix}合并利润表")
        primary = fee_subjects[0] if fee_subjects else "期间费用"
        _add(f"{prefix}合并利润表 {primary} 2024 2025")
        if _COMPARE_PAT.search(qj):
            _add(f"{prefix}母公司利润表 {primary} 2024 2025")
    elif tt == TaskType.compare:
        _add(f"{prefix}合并利润表 2024 2025")
        _add(f"{prefix}母公司利润表")
        _add(f"{prefix}主要会计数据 营业收入")
        if bs_subjects:
            _plan_bs_compare_subqueries(_add, prefix=prefix, subjects=bs_subjects)
        if cf_subjects:
            _plan_cf_compare_subqueries(_add, prefix=prefix, subjects=cf_subjects)
        if any(x in qj for x in ("明细", "费用", "分解")):
            _plan_fee_note_subqueries(
                _add,
                prefix=prefix,
                subjects=fee_subjects,
                wants_reason=wants_reason,
            )
        if wants_reason and not fee_subjects:
            _add(f"{prefix}期间费用 变动原因 说明")
            _add(f"{prefix}经营情况讨论 期间费用")
        if wants_analyst:
            _append_narrative_subqueries(_add, prefix=prefix, wants_analyst=True)
    elif tt == TaskType.process:
        _add(f"{prefix}流程 制度")
    elif tt == TaskType.fact and ent:
        if "营收" in qj or "收入" in q:
            _add(f"{prefix}合并利润表 营业收入")
        if bs_subjects:
            _plan_bs_compare_subqueries(_add, prefix=prefix, subjects=bs_subjects)
        if cf_subjects:
            _plan_cf_compare_subqueries(_add, prefix=prefix, subjects=cf_subjects)

    return out[:cap]
