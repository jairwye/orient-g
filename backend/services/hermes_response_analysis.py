"""Hermes 终稿/过程稿分类：探针实测后用于 MCP 优化与网关收束。"""

from __future__ import annotations

import re
from typing import Any

# Hermes 在 MCP 失败或空转时常见误判话术（非 KB 真实状态）
KB_EMPTY_HALLUCINATION_RE = re.compile(
    r"知识库(?:当前)?(?:为空|没有任何可用文档|访问受限|检索全部被拒绝)"
    r"|MCP(?:检索)?(?:全部被拒绝|无法获取数据|当前为空)"
    r"|无法通过\s*MCP\s*获取",
    re.I,
)

LISTED_COMPANY_DENIAL_RE = re.compile(
    r"没有名为[「\"']?YYCQ"
    r"|A股市场中.{0,12}没有.{0,12}YYCQ"
    r"|请确认.{0,20}哪家公司",
    re.I,
)

ENGLISH_PLANNING_RE = re.compile(
    r"Let me search|I need to find|The search results",
    re.I,
)


def hermes_reply_has_kb_empty_hallucination(text: str) -> bool:
    return bool(KB_EMPTY_HALLUCINATION_RE.search(text or ""))


def hermes_reply_has_listed_company_denial(text: str, *, user_query: str = "") -> bool:
    if not LISTED_COMPANY_DENIAL_RE.search(text or ""):
        return False
    if re.search(r"YYCQ", user_query or ""):
        return True
    return bool(re.search(r"YYCQ", text or ""))


def hermes_reply_has_english_planning(text: str) -> bool:
    return bool(ENGLISH_PLANNING_RE.search(text or ""))


def hermes_reply_has_personnel_speculation(text: str) -> bool:
    """人员/对照场景：推算、推断、无证据约N人、请勿采信掩盖。"""
    from backend.services.hermes_stream_sanitize import reply_has_unsupported_speculation

    return reply_has_unsupported_speculation(text or "")


def hermes_personnel_compare_quality_score(text: str, *, user_query: str = "") -> int:
    """
    人员横比稿质量分（越高越应作为 Hermes 有效终稿来源）。
    用于 resolve_hermes_effective_reply：避免 run.completed 长幻觉/推算覆盖过程稿。
    """
    h = (text or "").strip()
    if not h:
        return 0
    score = min(len(h) // 40, 25)
    if hermes_reply_has_kb_empty_hallucination(h):
        score -= 80
    if hermes_reply_has_listed_company_denial(h, user_query=user_query):
        score -= 60
    if hermes_reply_has_english_planning(h):
        score -= 30
    if hermes_reply_has_personnel_speculation(h):
        score -= 70
    if re.search(r"请勿采信", h):
        score -= 25
    from backend.services.kb_ask_mcp_agent_native import (
        is_personnel_mcp_draft_skeleton,
        is_personnel_thin_salvage_final,
    )

    if is_personnel_mcp_draft_skeleton(h):
        # 骨架/参考表标题上屏 ≠ Hermes 主写终稿
        score -= 90
    if is_personnel_thin_salvage_final(h):
        score -= 50
    if re.search(r"人员结构对照", h):
        score += 40
    if re.search(r"###\s*对比分析|对比分析", h):
        score += 20
    if re.search(r"1378|1[,，]?378", h):
        score += 15
    if re.search(r"\b946\b", h):
        score += 10
    if re.search(r"\b242\b", h):
        score += 10
    if re.search(r"\b70\b", h):
        score += 10
    if re.search(r"可比公司A|可比公司A", h) and re.search(r"YYCQ", h, re.I):
        score += 15
    if re.search(r"核心指标对比|22\.6\s*倍", h):
        score -= 25
    from backend.services.personnel_compare_report import (
        personnel_compare_hermes_draft_is_bad,
        personnel_compare_sanqi_table_incomplete,
    )

    if personnel_compare_sanqi_table_incomplete(h):
        score -= 50
    if user_query and personnel_compare_hermes_draft_is_bad(h, user_query=user_query):
        score -= 40
    return score


def classify_hermes_response(
    text: str,
    *,
    user_query: str = "",
) -> dict[str, Any]:
    """探针 runner / live 测试：归类 Hermes 回应模式。"""
    h = (text or "").strip()
    tags: list[str] = []
    if not h:
        tags.append("empty")
    if hermes_reply_has_kb_empty_hallucination(h):
        tags.append("kb_empty_hallucination")
    if hermes_reply_has_listed_company_denial(h, user_query=user_query):
        tags.append("listed_company_denial")
    if hermes_reply_has_english_planning(h):
        tags.append("english_planning")
    if hermes_reply_has_personnel_speculation(h):
        tags.append("unsupported_speculation")
    from backend.services.kb_ask_mcp_agent_native import (
        is_personnel_mcp_draft_skeleton,
        is_personnel_thin_salvage_final,
    )

    if is_personnel_mcp_draft_skeleton(h):
        tags.append("mcp_draft_skeleton")
    if is_personnel_thin_salvage_final(h):
        tags.append("thin_salvage_final")
    if re.search(r"人员结构对照", h):
        tags.append("personnel_structure_table")
    if re.search(r"权限受限|doc allowed scope empty", h, re.I):
        tags.append("permission_denied")
    q = (user_query or "").strip()
    personnel = bool(q and re.search(r"人员|员工|人效", q))
    score = hermes_personnel_compare_quality_score(h, user_query=q) if personnel else 0
    acceptable = (
        personnel
        and score >= 50
        and "kb_empty_hallucination" not in tags
        and "unsupported_speculation" not in tags
        and "mcp_draft_skeleton" not in tags
        and "thin_salvage_final" not in tags
    )
    return {
        "tags": tags,
        "personnel_quality_score": score,
        "len": len(h),
        "acceptable_personnel_final": acceptable,
    }
