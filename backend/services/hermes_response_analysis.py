"""Hermes 终稿/过程稿分类：探针实测后用于 MCP 优化与网关收束。"""

from __future__ import annotations

import re
from typing import Any

# Hermes 在 MCP 失败或空转时常见误判话术（非 KB 真实状态）
KB_EMPTY_HALLUCINATION_RE = re.compile(
    r"知识库(?:当前)?(?:为空|没有任何可用文档|访问受限|权限受限|检索全部被拒绝)"
    r"|知识库.{0,16}权限受限.{0,16}无法检索"
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
    r"Let me (?:first\b|search|retrieve|check|look|find|start)|"
    r"I'll (?:start|first|retrieve|check)|"
    r"I need to (?:find|retrieve|check|verify)|"
    r"The search results|Now let me\b|"
    r"verification_queries|next_action\s*=\s*verify_gap",
    re.I,
)

PROCESS_DRAFT_RE = re.compile(
    r"核证补缺|evidence_sufficient\s*=\s*false|"
    r"next_action\s*=\s*verify_gap_then_write_final|"
    r"我将继续调用\s*orientg_kb_ask|仍未成稿|"
    r"Let me first\b",
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


def hermes_reply_has_process_draft_markers(text: str) -> bool:
    """编排/核证过程语气（非面向用户的实质终稿）。"""
    h = text or ""
    if PROCESS_DRAFT_RE.search(h):
        return True
    from backend.services.hermes_stream_sanitize import looks_like_planning

    return looks_like_planning(h)


def _strip_for_user_facing_gate(text: str) -> str:
    """质量门前剥离编排前缀，避免「英文过程句+中文终稿」双稿误杀。"""
    h = (text or "").strip()
    if not h:
        return ""
    try:
        from backend.services.hermes_stream_sanitize import (
            extract_user_facing_reply,
            strip_hermes_orchestration_preamble,
        )

        cleaned = strip_hermes_orchestration_preamble(
            extract_user_facing_reply(h)
        ).strip()
        if cleaned and len(cleaned) >= 24:
            return cleaned
    except Exception:
        pass
    return h


def hermes_reply_has_substantive_draft(text: str, *, user_query: str = "") -> bool:
    """
    全局：已有可 salvage 的实质过程/终稿（含证据数字）。
    用于禁止假「未调 MCP」优先重试清稿毁流；不等于可验收 user-facing 终稿。
    """
    if hermes_reply_is_user_facing_final(text, user_query=user_query):
        return True
    raw = (text or "").strip()
    if len(raw) < 40:
        return False
    if re.search(r"证据不足|未给出合格|无法展示可靠对照|未完成可用终稿", raw):
        return False
    # 纯拒答/短占位不算实质
    if re.search(r"^#{0,3}\s*拒答\s*$", raw) or raw in ("## 拒答", "拒答"):
        return False
    h = _strip_for_user_facing_gate(raw)
    zh_n = len(re.findall(r"[\u4e00-\u9fff]", h))
    if zh_n < 20:
        return False
    # 实质：中文 + 证据数字 / 对照表结构 / 取证叙述
    if re.search(r"\d{2,}", h) and zh_n >= 20:
        return True
    if ("|" in h or "\t" in h or re.search(r"对照", h)) and zh_n >= 16:
        return True
    if re.search(r"取证|Evidence|citations|研发|人员|员工", h, re.I) and zh_n >= 28:
        return True
    return False


def hermes_reply_is_user_facing_final(text: str, *, user_query: str = "") -> bool:
    """
    全局质量门：终稿须为面向用户的实质中文答案。
    过程稿（英文 planning / 核证补缺计划 / MCP 编排独白）不得作为 final。
    人员/非人员共用同一标准：中文标题/对照表/分项表/分析即可；禁止人员专用硬放行数字。
    """
    raw = (text or "").strip()
    if len(raw) < 24:
        return False
    # 网关套话本身不是合格终稿
    if re.search(r"证据不足|未给出合格|无法展示可靠对照|未完成可用终稿", raw):
        return False
    h = _strip_for_user_facing_gate(raw)
    if len(h) < 24:
        return False
    if re.search(r"证据不足|未给出合格|无法展示可靠对照|未完成可用终稿", h):
        return False
    # 剥离后仍以英文 planning / 核证计划为主 → 过程稿
    if hermes_reply_has_english_planning(h) and not re.search(r"[\u4e00-\u9fff]{8,}", h):
        return False
    if PROCESS_DRAFT_RE.search(h) and not (
        re.search(r"对照|分析", h)
        or "|" in h
        or "\t" in h
        or re.search(r"^#{1,3}\s+\S+", h, re.M)
    ):
        return False
    from backend.services.hermes_stream_sanitize import looks_like_planning

    if looks_like_planning(h):
        # 过程语气残留时，须仍有实质中文报告结构
        has_structure = bool(
            (re.search(r"^#{1,3}\s+\S+", h, re.M) and len(re.findall(r"[\u4e00-\u9fff]", h)) >= 8)
            or (("|" in h or re.search(r"\t[^\t]+\t", h)) and re.search(r"\d", h))
            or (re.search(r"对照", h) and re.search(r"\d{2,}", h))
        )
        if re.search(r"Let me first\b", h, re.I) and not has_structure:
            return False
        if not has_structure:
            return False
    if not re.search(r"[\u4e00-\u9fff]", h):
        return False
    zh_n = len(re.findall(r"[\u4e00-\u9fff]", h))
    if re.search(r"^#{1,3}\s+\S+", h, re.M) and zh_n >= 8:
        return True
    if "|" in h and zh_n >= 4 and re.search(r"\d", h):
        return True
    # TSV / 纯文本分项表（浏览器 Hermes 常见）
    if re.search(r"\t[^\t]+\t", h) and zh_n >= 8 and re.search(r"\d{2,}", h):
        return True
    # 短中文金额/分项结论（lite 补检索终稿常见）
    if zh_n >= 4 and re.search(r"\d{1,3}(?:,\d{3})+\.\d{2}", h):
        return True
    if re.search(r"对照", h) and re.search(r"\d{2,}", h) and zh_n >= 12:
        return True
    if "分析" in h and len(h) >= 40 and zh_n >= 12:
        return True
    return len(h) >= 120 and zh_n >= 20


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
    # 通用：双侧分项数字与表格结构（禁止硬编码 1378/946/242/70 刷分）
    if re.search(r"(研发|运营|销售|管理).{0,24}\d{2,}", h):
        score += 15
    if ("|" in h or re.search(r"\t[^\t]+\t", h)) and len(re.findall(r"\d{2,}", h)) >= 3:
        score += 15
    from backend.services.kb_compare_entities import (
        PEER_ENTITY,
        PRIMARY_ENTITY,
        peer_aliases,
        primary_aliases,
    )

    peer_hit = PEER_ENTITY in h or any(a and a in h for a in peer_aliases())
    prim_hit = bool(re.search(re.escape(PRIMARY_ENTITY), h, re.I)) or any(
        a and a in h for a in primary_aliases()
    )
    if peer_hit and prim_hit:
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
    # 过程稿标签：有对照表标题的粘贴双稿另由 dual_draft / authorship 处理
    if "personnel_structure_table" not in tags and (
        PROCESS_DRAFT_RE.search(h) or hermes_reply_has_process_draft_markers(h)
    ):
        tags.append("process_draft")
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
        and "english_planning" not in tags
        and "process_draft" not in tags
    )
    return {
        "tags": tags,
        "personnel_quality_score": score,
        "len": len(h),
        "acceptable_personnel_final": acceptable,
    }
