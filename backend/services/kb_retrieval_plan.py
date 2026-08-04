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


_BREAKDOWN_PAT = re.compile(
    r"成本|费用|明细|拆解|分解|归因|下降|(?:费用|成本|收入|业务|产品|资产|资本)结构",
    re.I,
)
_PERSONNEL_PAT = re.compile(r"人员|员工|在职|人效|用工|headcount", re.I)
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
    if query_wants_personnel_structure(user_query):
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
    if _PERSONNEL_PAT.search(qj) and re.search(r"对比|比较", qj):
        return TaskType.compare
    if _PERSONNEL_PAT.search(qj):
        return TaskType.general
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


from backend.services.kb_compare_entities import (
    PRIMARY_ENTITY,
    PEER_ENTITY,
    compare_entity_markers,
    is_peer_text,
    is_primary_text,
)


def normalize_compare_entity_phrase(phrase: str) -> str:
    """横比问句实体清洗：去「对比分析」等前缀与「25年的人员结构」等后缀。"""
    s = (phrase or "").strip()
    for prefix in ("对比分析", "对比", "比较", "分析"):
        if s.startswith(prefix):
            s = s[len(prefix) :].strip()
    s = re.sub(r"\d{2,4}年.*$", "", s).strip()
    s = re.sub(r"的人员.*$", "", s).strip()
    qj = s.replace(" ", "")
    for marker in compare_entity_markers():
        if marker.replace(" ", "") in qj or marker in s:
            return marker
    return s


def extract_query_entity_phrases(user_query: str) -> list[str]:
    q = (user_query or "").strip()
    if not q:
        return []
    qj = q.replace(" ", "")
    found: list[str] = []
    seen: set[str] = set()

    def _add(s: str) -> None:
        s = normalize_compare_entity_phrase(s)
        if len(s) < 2 or s in seen:
            return
        seen.add(s)
        found.append(s)

    for marker in compare_entity_markers():
        if marker.replace(" ", "") in qj or marker in q:
            _add(marker)
    if len(found) >= 2:
        return found

    for m in re.finditer(r"([\u4e00-\u9fffA-Za-z0-9·]{2,12})(?:和|与|、)([\u4e00-\u9fffA-Za-z0-9·]{2,12})", q):
        _add(m.group(1))
        _add(m.group(2))
    ent = detect_entity(q)
    if ent:
        _add(ent)
    return found


def query_wants_personnel_structure(user_query: str) -> bool:
    qj = (user_query or "").replace(" ", "")
    return bool(_PERSONNEL_PAT.search(qj))


def _personnel_subject_entities(user_query: str) -> list[str]:
    """人员横比/专节：仅识别公司主体，排除「专业构成及教育程度」等误切词。"""
    q = (user_query or "").strip()
    found: list[str] = []
    if is_peer_text(q):
        found.append(PEER_ENTITY)
    if is_primary_text(q):
        found.append(PRIMARY_ENTITY)
    return found


def query_wants_personnel_compare(user_query: str) -> bool:
    """两家及以上主体的人员结构横比（浏览器验收主路径）。"""
    q = (user_query or "").strip()
    if not query_wants_personnel_structure(q):
        return False
    ents = _personnel_subject_entities(q)
    if len(ents) >= 2:
        return True
    return bool(re.search(r"(?:和|与|、).*(?:可比公司A|YYCQ|互娱|YYCQ)", q, re.I))


def native_personnel_prefetch_max_queries(
    user_query: str,
    *,
    prefetch_tier: str | None = None,
) -> int | None:
    """native + full/deep + 人员：返回 prefetch 子检索上限；None=沿用 legacy 多 query。

    目标 4：证据获取更多落在 Hermes MCP，减少网关连查（见 1.2.3.d §0.1）。
    """
    from backend.config import settings

    if not getattr(settings, "hermes_native_mcp_reply", False):
        return None
    if (prefetch_tier or "").strip().lower() != "full":
        return None
    if not query_wants_personnel_structure(user_query):
        return None
    return max(0, int(getattr(settings, "hermes_native_prefetch_max_kb_asks", 1) or 0))


def personnel_retrieval_subqueries(user_query: str) -> list[str]:
    """KB 人员结构：各主体 docling section（研发人员情况等）+ excel chunk（1.1信息-人员）。"""
    q = (user_query or "").strip()
    out: list[str] = []
    section_terms = (
        "研发人员情况",
        "员工情况",
        "员工数量、专业构成及教育程度",
        "1.1信息-人员",
        "在职员工",
    )
    for ent in extract_query_entity_phrases(q)[:3]:
        for term in section_terms:
            out.append(f"{ent} {term} 2025")
        out.append(f"{ent} 2025年末 员工人数")
        if re.search(r"可比公司A", ent):
            out.extend(
                [
                    f"{ent} 员工数量 专业构成及教育程度 2025",
                    f"{ent} 1、员工数量、专业构成及教育程度",
                    f"{ent} 员工情况 专业构成 2025",
                    f"{ent} 在职员工 人数 构成 2025",
                    f"{ent} 销售人员 运营人员 2025",
                ]
            )
    out.extend(
        [
            "研发人员情况 期末人数 占比 2025",
            "1.1信息-人员 2025全年",
            "公司研发人员 教育程度 期末人数",
        ]
    )
    return out


def enhance_kb_ask_query(query: str) -> str:
    """MCP/Hermes 宽问句补 KB 人员 section 锚点（docling / excel chunk）。"""
    q = (query or "").strip()
    if not q or not query_wants_personnel_structure(q):
        return q
    if re.search(r"研发人员|1\.1信息-人员|员工情况", q, re.I):
        return q
    return f"{q} 研发人员情况 员工人数 2025"


def plan_hermes_recovery_queries(user_query: str, *, max_queries: int = 2) -> list[str]:
    q = (user_query or "").strip()
    if not q:
        return []
    if query_wants_personnel_structure(q):
        out = [enhance_kb_ask_query(q)]
        for sq in personnel_retrieval_subqueries(q):
            if sq not in out:
                out.append(sq)
            if len(out) >= max(1, max_queries):
                break
        return out[: max(1, max_queries)]
    out = [q]
    for ent in extract_query_entity_phrases(q):
        cand = f"{ent} {q}"
        if cand not in out:
            out.append(cand)
        if len(out) >= max(1, max_queries):
            break
    return out[: max(1, max_queries)]


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
        if query_wants_personnel_structure(q):
            for sq in personnel_retrieval_subqueries(q):
                _add(sq)
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
