"""Evidence Pack 与 Agent 终稿的通用对齐（不绑定具体公司/科目/金额）。"""

from __future__ import annotations

import re
from typing import Any

_AMOUNT_RE = re.compile(r"\d{1,3}(?:,\d{3})+\.\d{2}")
_GAP_PLACEHOLDER_RE = re.compile(
    r"证据中未提供.+分项|无法按科目展开|费用明细说明|无法按科目|分项缺项|未提供变动原因"
)
_DERIVED_BREAKDOWN_RE = re.compile(
    r"计算得出|减去变动|反推|通过.{0,24}得出|"
    r"=\s*\d{1,3}(?:,\d{3})+\.\d{2}\s*[-−−]|"
    r"系根据.{0,40}减去|差异为四舍五入",
    re.I,
)
_REASON_CITED_RE = re.compile(
    r"主要系|主要是由于|系因|系由于|变动原因.*(?:主要|由于)|"
    r"人员减少|职工薪酬减少|市场推广.*增加",
    re.I,
)


def pack_evidence_blob(pack: dict[str, Any] | None) -> str:
    p = pack or {}
    parts = [
        str(f.get("excerpt") or "")
        for f in (p.get("facets") or [])
        if isinstance(f, dict)
    ]
    hits = p.get("facet_hits") or p.get("keywords_hit") or []
    if isinstance(hits, list):
        parts.append(" ".join(str(x) for x in hits))
    return "\n".join(parts)


def extract_tabular_amounts(text: str, *, limit: int = 12) -> list[str]:
    """从证据/正文中提取可核查金额（去重，按数值降序）。"""
    seen: set[str] = set()
    found: list[str] = []
    for m in _AMOUNT_RE.findall(text or ""):
        if m in seen:
            continue
        seen.add(m)
        found.append(m)

    def _num(s: str) -> float:
        try:
            return float(s.replace(",", ""))
        except ValueError:
            return 0.0

    found.sort(key=_num, reverse=True)
    return found[:limit]


def pack_has_tabular_breakdown(pack: dict[str, Any] | None, *, min_amounts: int = 3) -> bool:
    """pack 是否像「多行金额表/附注分项」（通用，不限销售费用）。"""
    blob = pack_evidence_blob(pack)
    amounts = extract_tabular_amounts(blob, limit=20)
    if len(amounts) < min_amounts:
        return False
    return bool(re.search(r"[\u4e00-\u9fff]{2,}", blob))


def reply_amount_coverage(reply: str, pack_amounts: list[str]) -> float:
    if not pack_amounts:
        return 1.0
    hits = sum(1 for a in pack_amounts if a in (reply or ""))
    return hits / len(pack_amounts)


def reply_has_gap_placeholder(reply: str) -> bool:
    return bool(_GAP_PLACEHOLDER_RE.search(reply or ""))


def reply_has_derived_breakdown_amounts(reply: str) -> bool:
    """分项金额通过加减/反推得出，非证据原文列示。"""
    for ln in (reply or "").split("\n"):
        if any(x in ln for x in ("禁止", "不得", "技能文档", "约束", "请勿采信")):
            continue
        if _DERIVED_BREAKDOWN_RE.search(ln):
            return True
    return False


def reply_falsely_denies_kb_breakdown(reply: str, *, user_query: str = "") -> bool:
    """模型声称 KB 无某科目明细，但问句明确要求分项（须触发补检索/修订）。"""
    from backend.services.kb_retrieval_plan import fee_subjects_from_query
    from backend.services.knowledge_pipeline import query_wants_fee_breakdown

    if not query_wants_fee_breakdown(user_query):
        return False
    t = reply or ""
    if not re.search(r"不包含|缺失|无法提供|没有.+明细|无法.+报告", t):
        return False
    subjects = fee_subjects_from_query(user_query)
    if subjects:
        return any(s in t for s in subjects)
    return "费用" in t or "明细" in t


def reply_has_contradictory_change_reason(reply: str) -> bool:
    """同篇报告既写「无变动原因」又引用原因原文。"""
    t = reply or ""
    if not reply_has_gap_placeholder(t):
        return False
    if not _REASON_CITED_RE.search(t):
        return False
    if re.search(r"证据未提供变动原因|未提供变动原因说明", t):
        return True
    return False


def reply_amount_in_pack(amount: str, pack: dict[str, Any] | None) -> bool:
    if not amount:
        return False
    return amount in pack_evidence_blob(pack)


def reply_has_compare_structure(reply: str) -> bool:
    """终稿是否具备对比报告结构（金额表、诚实缺证据表、结论段）。"""
    from backend.services.hermes_stream_sanitize import reply_has_verifiable_breakdown_table

    t = (reply or "").strip()
    if not t:
        return False
    if reply_has_verifiable_breakdown_table(t, min_data_rows=1):
        return True
    if re.search(r"(#{1,4}\s|^\d+\.\s|结论[：:]|结论概要)", t, re.M):
        return True
    pipe_rows = [
        ln
        for ln in t.splitlines()
        if ln.count("|") >= 2 and not re.match(r"\s*\|[-:\s|]+\|\s*$", ln)
    ]
    if len(pipe_rows) >= 2 and re.search(r"(缺少证据|20\d{2}|\d{1,3}(?:,\d{3})+\.\d{2})", t):
        return True
    if re.search(r"缺少证据|不确定/缺少证据", t) and re.search(
        r"(说明|需要证据|引用证据|\*\*说明\*\*)", t
    ):
        return True
    return bool(
        re.search(r"20\d{2}", t)
        and re.search(r"\d{1,3}(?:,\d{3})+\.\d{2}", t)
        and "|" in t
    )


def pack_amounts_for_alignment(pack: dict[str, Any] | None, *, limit: int = 10) -> list[str]:
    """用于对齐的 pack 锚点金额（排除过小噪声项时仍保留附注常见分项）。"""
    amounts = extract_tabular_amounts(pack_evidence_blob(pack), limit=limit + 4)
    if len(amounts) <= limit:
        return amounts
    return amounts[:limit]


def _citations_blob(citations: list[dict[str, Any]], pack: dict[str, Any] | None) -> str:
    blob = pack_evidence_blob(pack)
    for c in citations or []:
        if isinstance(c, dict):
            blob += "\n" + str(c.get("excerpt") or c.get("text") or "")
    return blob


def build_evidence_synth_fallback_reply(
    user_query: str,
    *,
    citations: list[dict[str, Any]],
    evidence_pack: dict[str, Any] | None = None,
) -> str:
    """LLM 合成超时/失败时的通用证据答复（不编造，仅摘录 pack/citations）。"""
    from backend.services.kb_evidence_probe import (
        blob_has_subject_near_amount,
        primary_compare_subject,
    )

    q = (user_query or "").strip()
    blob = _citations_blob(citations, evidence_pack)
    label = primary_compare_subject(q)
    amounts = extract_tabular_amounts(blob, limit=8)

    cite_ids: list[str] = []
    for c in citations or []:
        if not isinstance(c, dict):
            continue
        doc_id = str(c.get("doc_id") or "")
        if doc_id and doc_id not in cite_ids:
            cite_ids.append(doc_id)
        if len(cite_ids) >= 4:
            break

    if label and blob_has_subject_near_amount(blob, label):
        subject_lines = [ln.strip() for ln in blob.split("\n") if label in ln and _AMOUNT_RE.search(ln)]
        line_amounts = extract_tabular_amounts("\n".join(subject_lines[:6]), limit=4)
        if line_amounts:
            rows = "| 项目 | 金额（证据原文） |\n|---|---|\n"
            for i, amt in enumerate(line_amounts[:4], 1):
                rows += f"| {label}{' ' + str(i) if len(line_amounts) > 2 else ''} | {amt} |\n"
            body = (
                f"结论：证据中含「{label}」可核查金额（本地 LLM 综合超时，以下为证据摘录）。\n\n"
                f"{rows}\n"
                "说明：\n"
                "1. 本答复由证据 pack 直接摘录，未经过 LLM 二次综合。\n"
                "2. 若需完整对比表或变动原因，请重试或切换标准/深度档。\n"
            )
            if cite_ids:
                body += "\n引用证据：\n" + "\n".join(f"[doc_chunk {d}]" for d in cite_ids[:4])
            return body.strip()

    if label:
        gap = (
            f"结论：缺少证据。\n\n"
            f"| 项目 | 2025年 | 2024年 | 差额或同比 |\n"
            f"|---|---|---|---|\n"
            f"| {label} | 缺少证据 | 缺少证据 | 缺少证据 |\n\n"
            f"说明：\n"
            f"1. 已从知识库检索到 {len(citations)} 条证据，但本地 LLM 综合超时且证据中未找到「{label}」可核查金额。\n"
            f"2. 请缩小范围后重试，或切换标准/深度档。\n"
        )
        if cite_ids:
            gap += "\n引用证据：\n" + "\n".join(f"[doc_chunk {d}]" for d in cite_ids[:4])
        return gap.strip()

    if amounts:
        rows = "| 序号 | 证据金额 |\n|---|---|\n"
        for i, amt in enumerate(amounts[:4], 1):
            rows += f"| {i} | {amt} |\n"
        body = (
            f"结论：证据中含可核查金额（本地 LLM 综合超时，以下为摘录）。\n\n{rows}\n"
            f"说明：已从知识库检索到 {len(citations)} 条证据；未能完成 LLM 综合，请重试。\n"
        )
        if cite_ids:
            body += "\n引用证据：\n" + "\n".join(f"[doc_chunk {d}]" for d in cite_ids[:4])
        return body.strip()

    return (
        f"已从知识库检索到 {len(citations)} 条相关证据，但本地 LLM 综合超时且证据中未找到可核查金额。"
        "请缩小知识库范围后重试。"
    )
