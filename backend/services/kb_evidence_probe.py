"""KB 证据探测与终稿对齐（问句驱动，不绑定公司/固定 probe 表）。"""

from __future__ import annotations

import re
from typing import Any

from backend.services.evidence_reply_align import extract_tabular_amounts, pack_evidence_blob
from backend.services.kb_retrieval_plan import (
    compare_subjects_from_query,
    detect_entity,
    infer_task_type,
    plan_retrieval_queries,
)

_AMOUNT_RE = re.compile(r"\d{1,3}(?:,\d{3})+\.\d{2}")
_MISSING_RE = re.compile(
    r"缺少证据|无法提供对比|未提供.+具体数值|未包含.+数据|不确定/缺少证据|无法进行对比|未提供.+余额",
)
_SUBJECT_IN_MISSING_ROW = re.compile(
    r"\|\s*[^\n|]*(?:缺少证据|无法)[^\n|]*\|",
    re.I,
)

_LABEL_SUFFIXES = ("账面价值", "余额", "对比", "净额", "明细")


def normalize_compare_subject(subject: str) -> str:
    s = (subject or "").strip()
    for suf in _LABEL_SUFFIXES:
        s = s.replace(suf, "")
    return s.strip()


def primary_compare_subject(user_query: str, *, fallback: str = "") -> str:
    subjects = compare_subjects_from_query(user_query)
    if subjects:
        return normalize_compare_subject(subjects[0])
    return normalize_compare_subject(fallback)


def build_evidence_probe_query(user_query: str, *, entity: str | None = None) -> str:
    """从检索计划派生 probe 问句（实体 + 科目 + 报表类型，非写死 probe 表）。"""
    q = (user_query or "").strip()
    if not q:
        return q
    ent = (entity or "").strip() or detect_entity(q)
    tt = infer_task_type(q)
    planned = plan_retrieval_queries(q, tt, entity=ent, max_queries=8)
    primary = primary_compare_subject(q)
    qj = q.replace(" ", "")
    for sub in planned[1:]:
        sj = sub.replace(" ", "")
        if primary and primary in sj:
            return sub
    for sub in planned[1:]:
        sj = sub.replace(" ", "")
        if any(k in sj for k in ("资产负债表", "现金流量表", "利润表", "附注", "期末", "年末")):
            return sub
    if primary and ent:
        if "现金流" in qj:
            return f"{ent} {primary} 2024 2025"
        if any(x in qj for x in ("年末", "期末", "余额", "账面价值")):
            return f"{ent} {primary} 2024 2025 年末 余额"
        if any(x in qj for x in ("对比", "比较", "同比", "两年")):
            return f"{ent} {primary} 2024 2025"
    return planned[1] if len(planned) > 1 else q


def blob_has_subject_near_amount(blob: str, subject: str, *, window: int = 120) -> bool:
    """证据中科目标签与可核查金额共现（同行优先，邻近 fallback）。"""
    label = normalize_compare_subject(subject)
    if not label or not blob:
        return False
    for ln in blob.split("\n"):
        if label in ln and _AMOUNT_RE.search(ln):
            return True
    return bool(
        re.search(
            rf"{re.escape(label)}[^\n]{{0,{window}}}{_AMOUNT_RE.pattern}",
            blob,
        )
    )


def reply_says_honest_missing(reply: str) -> bool:
    t = reply or ""
    if not _MISSING_RE.search(t):
        return False
    if _AMOUNT_RE.search(t) and not _SUBJECT_IN_MISSING_ROW.search(t):
        return False
    return bool(_SUBJECT_IN_MISSING_ROW.search(t) or "缺少证据" in t or "不确定/缺少证据" in t)


def reply_matches_kb_evidence(
    reply: str,
    *,
    user_query: str,
    kb_probe: dict[str, Any],
    subject: str = "",
) -> bool:
    """KB 有数据则终稿须含锚点；KB 无数据则允许诚实缺少证据。"""
    from backend.services.hermes_stream_sanitize import finalize_agent_reply

    t = finalize_agent_reply(reply or "", user_query=user_query)
    if not kb_probe.get("has_data"):
        return reply_says_honest_missing(t) or bool(_AMOUNT_RE.search(t))
    if reply_says_honest_missing(t):
        return False
    anchors = kb_probe.get("anchors") or []
    if any(a in t for a in anchors[:4]):
        return True
    label = primary_compare_subject(user_query, fallback=subject)
    return bool(label) and label in t and bool(_AMOUNT_RE.search(t))


def probe_kb_evidence_for_query(
    token: str,
    user_query: str,
    scope: dict[str, Any],
    *,
    fixtures: dict[str, Any] | None = None,
    resolved_scope: dict[str, Any] | None = None,
    subject: str = "",
) -> dict[str, Any]:
    """对单条用户问句探测 KB 是否含可核查科目金额。"""
    from backend.services.kb_retrieve_pack import retrieve_kb_evidence_pack
    from backend.services.kb_scope_resolve import resolve_kb_scope_for_ask

    q = (user_query or "").strip()
    probe_q = build_evidence_probe_query(q)
    label = primary_compare_subject(q, fallback=subject)

    if fixtures is None:
        from backend.services.knowledge_acl import load_fixtures

        fixtures = load_fixtures()
    if resolved_scope is None:
        resolved_scope = resolve_kb_scope_for_ask("tenant1", scope)

    pack_res, _ = retrieve_kb_evidence_pack(
        token,
        probe_q,
        scope,
        fixtures=fixtures,
        resolved_scope=resolved_scope,
        multi_query=True,
    )
    pack = pack_res.get("evidence_pack") or {}
    blob = pack_evidence_blob(pack)
    for c in pack_res.get("citations") or []:
        if isinstance(c, dict):
            blob += "\n" + str(c.get("excerpt") or c.get("text") or "")

    anchors = extract_tabular_amounts(blob, limit=8)
    subject_near_amount = blob_has_subject_near_amount(blob, label) if label else bool(anchors)
    has_data = subject_near_amount if label else bool(anchors)

    return {
        "has_data": has_data,
        "anchors": anchors[:6],
        "subject": label or subject,
        "probe_query": probe_q,
        "subject_near_amount": subject_near_amount,
        "user_query": q,
    }
