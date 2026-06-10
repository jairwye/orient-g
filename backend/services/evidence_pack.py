"""Evidence Pack：多 query 检索结果的结构化证据包。"""

from __future__ import annotations

import re
from typing import Any

from backend.services.kb_retrieval_plan import TaskType

_PACK_VERSION = 1
_FEE_KWS = ("销售费用", "管理费用", "研发费用", "营业成本", "期间费用")
_COMPARE_KWS = ("营业收入", "净利润", "利润表", "合并利润表")


def merge_citations(citation_lists: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, ...]] = set()
    out: list[dict[str, Any]] = []
    for citations in citation_lists:
        for c in citations or []:
            if not isinstance(c, dict):
                continue
            key = (
                str(c.get("doc_id") or ""),
                str(c.get("chunk_id") or ""),
                str(c.get("table_id") or ""),
                str(c.get("row_key") or ""),
                str(c.get("column_id") or ""),
            )
            if key in seen:
                continue
            seen.add(key)
            out.append(c)
    return out[:40]


def _facet_label_from_text(txt: str) -> str:
    t = (txt or "").strip()
    m = re.search(r"^##\s*([^\n]+)", t)
    if m:
        return m.group(1).strip()[:80]
    m2 = re.search(r"##\s*\d+\s*[、.\s]*销售费用|##\s*销售费用", t)
    if m2:
        return m2.group(0).replace("#", "").strip()[:80]
    for kw in ("合并利润表", "母公司利润表", "销售费用", "管理费用", "营业收入"):
        if kw in t:
            return kw
    return "文档片段"


def _keywords_in_text(txt: str) -> list[str]:
    return [k for k in _FEE_KWS + _COMPARE_KWS + ("附注", "流程", "制度") if k in (txt or "")]


def build_evidence_pack(
    *,
    user_query: str,
    task_type: str,
    retrieval_queries: list[str],
    citations: list[dict[str, Any]],
    reply_parts: list[str],
    tenant_id: str,
    fixtures: dict[str, Any],
    chunk_texts: dict[str, str] | None = None,
    excerpt_cap: int = 2000,
    max_facets: int = 8,
    doc_folder_labels: dict[str, str] | None = None,
    multi_company_scope: bool = False,
    finance_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """chunk_texts: 可选预加载 \"doc_id:chunk_id\" -> text。"""
    from backend.services.agent_kb_prefetch import _top_citations_for_llm
    from backend.services.ai_interaction_llm import _load_doc_chunk_text

    tt = task_type or TaskType.general.value
    texts = dict(chunk_texts or {})
    labels = doc_folder_labels or {}
    max_per_doc = 2 if tt == TaskType.breakdown.value else 1
    facet_limit = max(max_facets, 12) if multi_company_scope else max_facets
    top = _top_citations_for_llm(
        list(citations or []),
        user_query,
        limit=facet_limit,
        tenant_id=tenant_id,
        fixtures=fixtures,
        max_chunks_per_doc=max_per_doc,
        doc_folder_labels=labels,
        multi_company_scope=multi_company_scope,
    )
    facets: list[dict[str, Any]] = []
    all_hits: set[str] = set()

    for c in top:
        if str(c.get("evidence_type") or "") == "table_row" or c.get("table_id"):
            tbl = str(c.get("table_id") or "")
            rk = str(c.get("row_key") or "")
            col = str(c.get("column_id") or "")
            label = f"表 {tbl}" + (f" · {rk}" if rk else "")
            excerpt = f"{col}={c.get('answer_value', '')}".strip("=") if col else ""
            if not excerpt and rk:
                excerpt = rk
            kws = _keywords_in_text(excerpt)
            all_hits.update(kws)
            facets.append(
                {
                    "label": label[:80],
                    "table_id": tbl,
                    "row_key": rk or None,
                    "column_id": col or None,
                    "excerpt": (excerpt or label)[:excerpt_cap],
                    "keywords_hit": kws,
                }
            )
            continue
        did = str(c.get("doc_id") or "")
        cid = str(c.get("chunk_id") or "") if c.get("chunk_id") else None
        cache_key = f"{did}:{cid or ''}"
        txt = texts.get(cache_key)
        if txt is None and did.startswith("ud_"):
            txt = _load_doc_chunk_text(tenant_id, did, cid, c.get("chunk_seq_no")) or ""
            texts[cache_key] = txt
        kws = _keywords_in_text(txt)
        all_hits.update(kws)
        excerpt = (txt or "")[:excerpt_cap]
        label = _facet_label_from_text(txt)
        src = labels.get(did, "").strip()
        if src:
            label = f"{src} · {label}"[:80]
            excerpt = f"[来源: {src}]\n{excerpt}"
        facets.append(
            {
                "label": label,
                "doc_id": did,
                "chunk_id": cid,
                "excerpt": excerpt,
                "keywords_hit": kws,
            }
        )

    evidence_text = "\n".join(str(f.get("excerpt") or "") for f in facets)
    gaps = _compute_gaps(
        tt,
        user_query,
        all_hits,
        len(citations or []),
        evidence_text=evidence_text,
        finance_meta=finance_meta,
    )
    score = _coverage_score(tt, len(citations or []), len(facets), all_hits, gaps, finance_meta=finance_meta)

    out_pack = {
        "version": _PACK_VERSION,
        "task_type": tt,
        "user_query": (user_query or "")[:800],
        "retrieval_queries": list(retrieval_queries or []),
        "facets": facets,
        "gaps": gaps,
        "coverage_score": round(score, 3),
        "citations": list(citations or []),
        "reply": " ".join(p for p in (reply_parts or []) if p).strip(),
    }
    if finance_meta and finance_meta.get("active"):
        out_pack["finance_meta"] = {
            "regime_id": finance_meta.get("regime_id"),
            "subject_type": finance_meta.get("subject_type"),
            "entity": finance_meta.get("entity"),
        }
    return out_pack


_REASON_GAP_KWS = (
    "主要系",
    "主要是由于",
    "是由于",
    "变动原因",
    "经营情况讨论",
    "管理层讨论",
    "项目重大变动原因",
    "职工薪酬减少",
    "人员减少",
)


def _has_change_reason_evidence(hits: set[str], evidence_text: str) -> bool:
    blob = (evidence_text or "").replace(" ", "")
    if any(k.replace(" ", "") in blob for k in _REASON_GAP_KWS):
        return True
    return any(k in hits for k in _REASON_GAP_KWS)


def _compute_gaps(
    task_type: str,
    user_query: str,
    hits: set[str],
    cite_count: int,
    *,
    evidence_text: str = "",
    finance_meta: dict[str, Any] | None = None,
) -> list[str]:
    gaps: list[str] = []
    qj = (user_query or "").replace(" ", "")
    if cite_count == 0:
        gaps.append("检索未命中任何文档片段")
        return gaps
    if finance_meta and finance_meta.get("active"):
        from backend.services.finance_annual_report_profile import finance_pack_gaps

        gaps.extend(
            finance_pack_gaps(
                user_query,
                task_type,
                evidence_text=evidence_text,
                finance_meta=finance_meta,
            )
        )
    if task_type == TaskType.breakdown.value:
        if any(x in qj for x in ("成本", "费用", "明细", "分解", "拆解")):
            if "销售费用" not in hits and "管理费用" not in hits:
                gaps.append("未命中销售费用或管理费用附注/利润表行")
            if "营业成本" not in hits and "成本" in qj:
                gaps.append("未命中营业成本相关片段")
    if task_type == TaskType.compare.value:
        skip_pl_gap = bool(
            finance_meta
            and finance_meta.get("active")
            and finance_meta.get("subject_type") in ("balance_sheet", "cash_flow")
        )
        if not skip_pl_gap and "营业收入" not in hits and not any(k in hits for k in ("利润表", "合并利润表")):
            blob = (evidence_text or "").replace(" ", "")
            if "营业收入" not in blob and "合并利润表" not in blob:
                gaps.append("未命中合并利润表或营业收入字段")
    from backend.services.kb_retrieval_plan import query_wants_change_reasons

    if query_wants_change_reasons(user_query):
        if not _has_change_reason_evidence(hits, evidence_text):
            gaps.append("未命中费用变动的文字性原因说明（若仅有金额表，答复中须说明）")
    return gaps


def _coverage_score(
    task_type: str,
    cite_count: int,
    facet_count: int,
    hits: set[str],
    gaps: list[str],
    finance_meta: dict[str, Any] | None = None,
) -> float:
    if cite_count == 0:
        return 0.0
    base = min(1.0, cite_count / 10.0) * 0.35 + min(1.0, facet_count / 5.0) * 0.35
    if gaps:
        base *= max(0.35, 1.0 - 0.2 * len(gaps))
    if task_type == TaskType.breakdown.value:
        fee_hits = sum(1 for k in ("销售费用", "管理费用", "营业成本") if k in hits)
        base += min(0.3, fee_hits * 0.1)
    elif task_type == TaskType.compare.value:
        st = str((finance_meta or {}).get("subject_type") or "")
        if st == "balance_sheet":
            base += 0.1
        elif st == "cash_flow":
            base += 0.1
        elif "营业收入" in hits or "合并利润表" in hits:
            base += 0.2
    elif task_type == TaskType.fact.value:
        base += 0.15 if facet_count >= 1 else 0.0
    return min(1.0, base)


def pack_coverage_sufficient(
    pack: dict[str, Any] | None,
    *,
    user_query: str = "",
    citations: list[dict[str, Any]] | None = None,
) -> bool:
    if not pack:
        return False
    if pack.get("gaps"):
        tt = str(pack.get("task_type") or "")
        if tt == TaskType.breakdown.value:
            return False
        if tt == TaskType.compare.value and float(pack.get("coverage_score") or 0) < 0.55:
            return False
    score = float(pack.get("coverage_score") or 0)
    tt = str(pack.get("task_type") or TaskType.general.value)
    cites = list(citations if citations is not None else (pack.get("citations") or []))
    if not cites:
        return False
    if tt == TaskType.fact.value:
        return score >= 0.45 and len(cites) >= 1
    if tt == TaskType.breakdown.value:
        facets = pack.get("facets") or []
        hits: set[str] = set()
        for f in facets:
            hits.update(f.get("keywords_hit") or [])
        if "销售费用" in hits or "管理费用" in hits:
            return score >= 0.5
        return False
    if tt == TaskType.compare.value:
        return score >= 0.55 and len(cites) >= 2
    return score >= 0.5


def query_needs_hermes_orchestration(user_query: str, pack: dict[str, Any] | None) -> bool:
    q = (user_query or "").strip()
    if re.search(r"核实|再查|验证|多轮", q):
        return True
    if not pack:
        return True
    tt = str(pack.get("task_type") or "")
    gaps = pack.get("gaps") or []
    if gaps and tt in (TaskType.compare.value, TaskType.breakdown.value):
        return True
    if tt in (TaskType.compare.value, TaskType.breakdown.value) and re.search(
        r"明细|分项|构成|附注|对比|比较|两年|报告",
        q,
    ):
        return True
    if float(pack.get("coverage_score") or 0) < 0.4:
        return True
    return False


def pack_summary_for_sse(pack: dict[str, Any] | None) -> dict[str, Any] | None:
    if not pack:
        return None
    return {
        "task_type": pack.get("task_type"),
        "gaps": pack.get("gaps"),
        "coverage_score": pack.get("coverage_score"),
        "retrieval_queries": pack.get("retrieval_queries"),
    }
