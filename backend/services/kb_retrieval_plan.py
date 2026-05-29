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


def plan_retrieval_queries(
    user_query: str,
    task_type: TaskType | str,
    *,
    entity: str | None = None,
    max_queries: int = 4,
) -> list[str]:
    """首条始终为用户原问；其余为定向子 query。"""
    q = (user_query or "").strip()
    if not q:
        return []
    tt = TaskType(task_type) if isinstance(task_type, str) else task_type
    ent = (entity or "").strip() or detect_entity(q)
    prefix = f"{ent} " if ent else ""
    out = [q]

    def _add(s: str) -> None:
        s = (s or "").strip()
        if s and s not in out and len(out) < max_queries:
            out.append(s)

    if tt == TaskType.breakdown:
        _add(f"{prefix}销售费用 附注")
        _add(f"{prefix}管理费用 附注")
        _add(f"{prefix}## 销售费用")
        _add(f"{prefix}营业成本 变动原因")
        _add(f"{prefix}合并利润表")
    elif tt == TaskType.compare:
        _add(f"{prefix}合并利润表 2024 2025")
        _add(f"{prefix}母公司利润表")
        _add(f"{prefix}主要会计数据 营业收入")
    elif tt == TaskType.process:
        _add(f"{prefix}流程 制度")
    elif tt == TaskType.fact and ent:
        if "营收" in q.replace(" ", "") or "收入" in q:
            _add(f"{prefix}合并利润表 营业收入")

    return out[:max_queries]
