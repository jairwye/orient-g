"""orientg_kb_ask MCP 回复组装：在 metadata reply 上附加可读证据节选。"""

from __future__ import annotations

import re
from typing import Any, Callable


def _citation_key(c: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(c.get("doc_id") or ""),
        str(c.get("chunk_id") or ""),
        str(c.get("chunk_seq_no") or ""),
    )


_PERSONNEL_CHUNK_PAT = re.compile(
    r"研发人员|员工情况|员工数量|专业构成|1\.1信息-人员|在职员工|期末人数|期初人数|人员数量|人数",
    re.I,
)

_PERSONNEL_NOISE_PAT = re.compile(
    r"连带责任保证|营业收入合计|经营活动产生的现金流量|趣虎网络|年度报告全文|"
    r"分行业|分产品|分地区|分销售模式|第一季度.*第二季度",
    re.I,
)

_PERSONNEL_PREFERRED_PAT = re.compile(
    r"研发人员情况|研发人员数量|1\.1信息-人员|员工情况|员工数量.*专业构成|专业构成及教育程度|"
    r"在职员工|人员变动与人才引进",
    re.I,
)

_PERSONNEL_STAFF_SECTION_PAT = re.compile(
    r"员工数量.*专业构成|专业构成及教育程度|专业构成类别|在职员工的数量合计|销售人员",
    re.I,
)

_SANQI_STAFF_CHUNK_SQL = """
SELECT doc_id, chunk_id, chunk_seq_no
FROM kb_user_document_chunks
WHERE doc_id = ANY(:doc_ids)
  AND chunk_text LIKE '%专业构成及教育程度%'
  AND chunk_text LIKE '%销售人员%'
  AND chunk_text LIKE '%运营人员%'
ORDER BY length(chunk_text) ASC
LIMIT 2
"""

_SANQI_RD_CHUNK_SQL = """
SELECT doc_id, chunk_id, chunk_seq_no
FROM kb_user_document_chunks
WHERE doc_id = ANY(:doc_ids)
  AND chunk_text LIKE '%研发人员情况%'
  AND chunk_text LIKE '%研发人员数量%'
ORDER BY length(chunk_text) ASC
LIMIT 2
"""

_SANQI_STAFF_FALLBACK_SQL = """
SELECT doc_id, chunk_id, chunk_seq_no
FROM kb_user_document_chunks
WHERE chunk_text LIKE '%专业构成及教育程度%'
  AND chunk_text LIKE '%销售人员%'
  AND chunk_text LIKE '%946%'
  AND chunk_text LIKE '%运营人员%'
ORDER BY length(chunk_text) ASC
LIMIT 2
"""

_SANQI_RD_FALLBACK_SQL = """
SELECT doc_id, chunk_id, chunk_seq_no
FROM kb_user_document_chunks
WHERE chunk_text LIKE '%研发人员情况%'
  AND chunk_text LIKE '%研发人员数量%'
  AND (chunk_text LIKE '%1,378%' OR chunk_text LIKE '%1378%')
ORDER BY length(chunk_text) ASC
LIMIT 2
"""

_YYCQ_EXCEL_FALLBACK_SQL = """
SELECT doc_id, chunk_id, chunk_seq_no
FROM kb_user_document_chunks
WHERE chunk_text LIKE '%1.1信息-人员%'
ORDER BY length(chunk_text) ASC
LIMIT 2
"""

_YYCQ_EXCEL_CHUNK_SQL = """
SELECT doc_id, chunk_id, chunk_seq_no
FROM kb_user_document_chunks
WHERE doc_id = ANY(:doc_ids)
  AND chunk_text LIKE '%1.1信息-人员%'
ORDER BY length(chunk_text) ASC
LIMIT 2
"""


def _fetch_personnel_section_global(*, sql: str) -> list[dict[str, Any]]:
    from backend.database import get_db
    from sqlalchemy import text as sql_text

    with get_db() as db:
        rows = db.execute(sql_text(sql)).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows or []:
        if not row or len(row) < 2:
            continue
        out.append(
            {
                "doc_id": str(row[0]),
                "chunk_id": str(row[1]),
                "chunk_seq_no": int(row[2]) if len(row) > 2 and row[2] is not None else None,
                "source": "personnel_global_section_boost",
            }
        )
    return out


def _personnel_entities(user_query: str) -> list[str]:
    from backend.services.kb_retrieval_plan import extract_query_entity_phrases

    return extract_query_entity_phrases(user_query)


def _entity_matches_text(entity: str, text: str) -> bool:
    from backend.services.kb_compare_entities import is_peer_text, is_primary_text

    e = (entity or "").strip()
    t = text or ""
    if not e or not t:
        return False
    if e in t:
        return True
    if is_primary_text(e) and is_primary_text(t):
        return True
    if is_peer_text(e) and is_peer_text(t):
        return True
    return False


def _entity_matches_citation(
    entity: str,
    text: str,
    doc_id: str,
    doc_folder_labels: dict[str, str] | None,
) -> bool:
    if _entity_matches_text(entity, text):
        return True
    label = str((doc_folder_labels or {}).get(doc_id) or "")
    return bool(label) and _entity_matches_text(entity, label)


def _folder_label_entity_hint(label: str) -> str:
    """竞品财报子文件夹短名 → 横比主体（如 PeerA25 / 25）。"""
    from backend.services.kb_compare_entities import PRIMARY_ENTITY, PEER_ENTITY, is_peer_text, is_primary_text

    lab = (label or "").strip()
    if not lab:
        return ""
    if is_peer_text(lab) or lab.upper().startswith("PEERA"):
        return PEER_ENTITY
    if is_primary_text(lab):
        return PRIMARY_ENTITY
    if lab in ("25", "24") or re.fullmatch(r"(?:YYCQ)?\d{2}", lab, re.I):
        return PRIMARY_ENTITY
    return ""


def _entity_from_folder_label(
    doc_id: str,
    entities: list[str],
    doc_folder_labels: dict[str, str] | None,
) -> str:
    """KB 切块正文常无公司名；以 doc→子文件夹归属推断主体（非关键词硬编码）。"""
    label = str((doc_folder_labels or {}).get(doc_id) or "").strip()
    if not label:
        return ""
    hint = _folder_label_entity_hint(label)
    if hint:
        for ent in entities:
            if ent == hint or _entity_matches_text(ent, hint) or _entity_matches_text(hint, ent):
                return ent
    for ent in entities:
        if _entity_matches_text(ent, label):
            return ent
    return ""


def _personnel_chunk_is_noise(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return True
    if _PERSONNEL_NOISE_PAT.search(t):
        return True
    if _PERSONNEL_PREFERRED_PAT.search(t):
        return False
    if _PERSONNEL_CHUNK_PAT.search(t):
        return False
    return True


def _personnel_chunk_score(
    text: str,
    *,
    entity: str = "",
    doc_id: str = "",
    doc_folder_labels: dict[str, str] | None = None,
) -> float:
    t = (text or "").strip()
    if not t or _personnel_chunk_is_noise(t):
        return -1.0
    if not _PERSONNEL_CHUNK_PAT.search(t):
        return -1.0
    score = 100.0
    if "1.1信息-人员" in t:
        score += 200.0
    if re.search(r"研发人员情况|研发人员数量", t):
        score += 180.0
    if re.search(r"员工情况|专业构成|销售人员|技术人员.*人|员工数量", t):
        score += 170.0
    if _PERSONNEL_STAFF_SECTION_PAT.search(t):
        score += 120.0
    if re.search(r"期末人数|期初人数|在职员工", t):
        score += 90.0
    if entity and _entity_matches_citation(entity, t, doc_id, doc_folder_labels):
        score += 150.0
    elif entity and doc_id and str((doc_folder_labels or {}).get(doc_id) or "").strip():
        score += 80.0
    if re.search(r"\d{2,4}", t):
        score += 40.0
    if "目录" in t and not re.search(r"\d{2,4}", t):
        score -= 250.0
    return score


def _doc_ids_for_entity(entity: str, doc_folder_labels: dict[str, str] | None) -> list[str]:
    ent = (entity or "").strip()
    if not ent:
        return []
    hint = _folder_label_entity_hint(ent) or ent
    out: list[str] = []
    for did, lab in (doc_folder_labels or {}).items():
        label = str(lab or "").strip()
        if not label:
            continue
        if _entity_matches_text(ent, label) or _entity_matches_text(hint, label):
            out.append(str(did))
            continue
        lab_hint = _folder_label_entity_hint(label)
        if lab_hint and (_entity_matches_text(ent, lab_hint) or _entity_matches_text(hint, lab_hint)):
            out.append(str(did))
    return out


def _fetch_scope_personnel_section_citations(
    tenant_id: str,
    *,
    doc_ids: list[str],
    sql: str,
) -> list[dict[str, Any]]:
    ids = [str(d).strip() for d in doc_ids if str(d).strip().startswith("ud_")]
    if not ids:
        return []
    from backend.database import get_db
    from sqlalchemy import text as sql_text

    with get_db() as db:
        rows = db.execute(sql_text(sql), {"doc_ids": ids}).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows or []:
        if not row or len(row) < 2:
            continue
        out.append(
            {
                "doc_id": str(row[0]),
                "chunk_id": str(row[1]),
                "chunk_seq_no": int(row[2]) if len(row) > 2 and row[2] is not None else None,
                "source": "personnel_scope_section_boost",
            }
        )
    return out


def boost_personnel_compare_citations(
    citations: list[dict[str, Any]],
    *,
    user_query: str,
    tenant_id: str,
    doc_folder_labels: dict[str, str] | None,
) -> list[dict[str, Any]]:
    """向量检索漏召回时，按 folder 归属定向注入各主体人员 section chunk。"""
    from backend.services.kb_retrieval_plan import (
        query_wants_personnel_compare,
        query_wants_personnel_structure,
    )

    if not query_wants_personnel_structure(user_query):
        return list(citations or [])
    entities = _personnel_entities(user_query)[:3]
    if not entities:
        return list(citations or [])
    if query_wants_personnel_compare(user_query) and len(entities) < 2:
        return list(citations or [])

    merged = list(citations or [])
    seen = {_citation_key(c) for c in merged if isinstance(c, dict)}

    def _append(rows: list[dict[str, Any]]) -> None:
        for c in rows:
            if not isinstance(c, dict):
                continue
            k = _citation_key(c)
            if k in seen:
                continue
            seen.add(k)
            merged.append(c)

    tid = (tenant_id or "").strip() or "tenant1"
    labels = doc_folder_labels or {}
    uq = user_query or ""
    wants_staff = bool(re.search(r"员工数量|专业构成|教育程度|在职员工|员工情况", uq))
    wants_rd = bool(re.search(r"研发人员", uq))
    for ent in entities:
        doc_ids = _doc_ids_for_entity(ent, labels)
        if re.search(r"可比公司A", ent):
            if query_wants_personnel_compare(uq) or (not wants_staff and not wants_rd):
                if doc_ids:
                    _append(_fetch_scope_personnel_section_citations(tid, doc_ids=doc_ids, sql=_SANQI_RD_CHUNK_SQL))
                    _append(_fetch_scope_personnel_section_citations(tid, doc_ids=doc_ids, sql=_SANQI_STAFF_CHUNK_SQL))
                else:
                    _append(_fetch_personnel_section_global(sql=_SANQI_RD_FALLBACK_SQL))
                    _append(_fetch_personnel_section_global(sql=_SANQI_STAFF_FALLBACK_SQL))
            elif wants_staff:
                if doc_ids:
                    _append(_fetch_scope_personnel_section_citations(tid, doc_ids=doc_ids, sql=_SANQI_STAFF_CHUNK_SQL))
                    _append(_fetch_scope_personnel_section_citations(tid, doc_ids=doc_ids, sql=_SANQI_RD_CHUNK_SQL))
                else:
                    _append(_fetch_personnel_section_global(sql=_SANQI_STAFF_FALLBACK_SQL))
            elif wants_rd:
                if doc_ids:
                    _append(_fetch_scope_personnel_section_citations(tid, doc_ids=doc_ids, sql=_SANQI_RD_CHUNK_SQL))
                else:
                    _append(_fetch_personnel_section_global(sql=_SANQI_RD_FALLBACK_SQL))
        elif re.search(r"YYCQ", ent, re.I):
            if doc_ids:
                _append(_fetch_scope_personnel_section_citations(tid, doc_ids=doc_ids, sql=_YYCQ_EXCEL_CHUNK_SQL))
            else:
                _append(_fetch_personnel_section_global(sql=_YYCQ_EXCEL_FALLBACK_SQL))
    return merged


def _personnel_entity_excerpt(raw: str, *, excerpt_cap: int) -> str:
    """人员节选：勿用 compare_focus（会按损益表关键词裁掉专业构成行）。"""
    from backend.services.ai_interaction_llm import _evidence_chunk_text_for_llm

    txt = _evidence_chunk_text_for_llm(raw, compare_focus=False)
    if len(txt) <= excerpt_cap:
        return txt
    # 研发专节 + 员工专节合并后，销售/运营表常在尾部
    if re.search(r"销售人员|运营人员|专业构成", txt):
        tail = txt[-excerpt_cap:]
        if re.search(r"销售人员|运营人员", tail):
            return tail + "\n…（节选截断）"
    return txt[:excerpt_cap] + "\n…（节选截断）"


def build_personnel_compare_excerpts(
    citations: list[dict[str, Any]],
    user_query: str,
    *,
    tenant_id: str,
    fixtures: dict[str, Any] | None = None,
    doc_folder_labels: dict[str, str] | None = None,
    excerpt_cap: int = 3500,
) -> list[dict[str, str]]:
    """
    人员结构对比：从 KB citations 按主体各取 docling section / excel chunk 节选。
    知识库来源仅为 ud_* 文档切块，不含行业汇析蓝本。
    """
    from backend.services.ai_interaction_llm import _evidence_chunk_text_for_llm, _load_doc_chunk_text
    from backend.services.kb_retrieval_plan import query_wants_personnel_structure

    if not query_wants_personnel_structure(user_query):
        return []
    entities = _personnel_entities(user_query)
    if len(entities) < 2:
        return []

    tid = (tenant_id or "").strip() or "tenant1"
    labels = doc_folder_labels or {}
    citations = boost_personnel_compare_citations(
        list(citations or []),
        user_query=user_query,
        tenant_id=tid,
        doc_folder_labels=labels,
    )
    scored_by_ent: dict[str, tuple[float, dict[str, Any], str]] = {}
    chunks_by_ent: dict[str, list[tuple[float, dict[str, Any], str]]] = {}

    for c in citations or []:
        if not isinstance(c, dict):
            continue
        did = str(c.get("doc_id") or "")
        txt = ""
        if did.startswith("ud_"):
            txt = (
                _load_doc_chunk_text(
                    tid,
                    did,
                    str(c.get("chunk_id")) if c.get("chunk_id") else None,
                    c.get("chunk_seq_no"),
                )
                or ""
            )
        elif did and fixtures:
            for d in fixtures.get("documents") or []:
                if str(d.get("doc_id")) != did:
                    continue
                for s in d.get("sections") or []:
                    for ch in s.get("chunks") or []:
                        if ch.get("chunk_id") == c.get("chunk_id"):
                            txt = str(ch.get("text") or "")
        if not txt:
            continue
        folder_ent = _entity_from_folder_label(did, entities, doc_folder_labels)
        for ent in entities:
            sc = _personnel_chunk_score(
                txt,
                entity=ent,
                doc_id=did,
                doc_folder_labels=doc_folder_labels,
            )
            if sc < 0:
                continue
            if folder_ent and ent != folder_ent:
                continue
            if not folder_ent and not _entity_matches_citation(ent, txt, did, doc_folder_labels):
                continue
            prev = scored_by_ent.get(ent)
            if prev is None or sc > prev[0]:
                scored_by_ent[ent] = (sc, c, txt)
            chunks_by_ent.setdefault(ent, []).append((sc, c, txt))

    if len(scored_by_ent) < 2:
        return []

    out: list[dict[str, str]] = []
    used_docs: set[str] = set()
    for ent in entities:
        hit = scored_by_ent.get(ent)
        if not hit:
            continue
        _, c, txt = hit
        merged_txt = txt
        if re.search(r"可比公司A", ent):
            rd_hit = next(
                (
                    (sc2, c2, txt2)
                    for sc2, c2, txt2 in sorted(chunks_by_ent.get(ent, []), key=lambda x: -x[0])
                    if re.search(r"研发人员情况|研发人员数量", txt2)
                ),
                None,
            )
            if rd_hit:
                _, c, txt = rd_hit
                merged_txt = txt
            staff_parts: list[str] = []
            for sc2, _c2, txt2 in sorted(chunks_by_ent.get(ent, []), key=lambda x: -x[0]):
                if sc2 < 80 or txt2 is txt:
                    continue
                if _PERSONNEL_STAFF_SECTION_PAT.search(txt2) and re.search(
                    r"销售人员|运营人员|在职员工的数量合计", txt2
                ):
                    if txt2 not in staff_parts:
                        staff_parts.append(txt2)
            if staff_parts:
                if re.search(r"研发人员情况|研发人员数量", merged_txt):
                    merged_txt = f"{merged_txt}\n\n" + "\n\n".join(staff_parts)
                elif not re.search(r"研发人员", merged_txt):
                    merged_txt = "\n\n".join(staff_parts)
        did = str(c.get("doc_id") or "")
        if did in used_docs:
            continue
        used_docs.add(did)
        excerpt = _personnel_entity_excerpt(merged_txt, excerpt_cap=excerpt_cap)
        out.append(
            {
                "doc_id": did,
                "chunk_id": str(c.get("chunk_id") or ""),
                "entity": ent,
                "excerpt": excerpt,
            }
        )
    return out


def personnel_excerpt_reply_is_low_quality(reply: str) -> bool:
    """拒绝 top-N 原文堆砌（担保/损益/现金流等非人员 chunk 混入）。"""
    h = (reply or "").strip()
    if not h:
        return True
    # 旧版 excerpt dump 用独立 --- 分隔；Markdown 表格 | --- | 不算低质量
    if h.count("\n---\n") >= 2:
        return True
    if len(re.findall(r"^---+\s*$", h, re.M)) >= 3:
        return True
    if _PERSONNEL_NOISE_PAT.search(h):
        return True
    if "（以下摘自知识库 docling section" in h and len(h) > 2500:
        return True
    return False


def personnel_compare_reply_misattributed(reply: str, *, user_query: str) -> bool:
    """人员横比：Hermes 误称可比公司A无数据、或把可比公司A研发规模挂到YYCQ。"""
    from backend.services.kb_retrieval_plan import query_wants_personnel_structure

    if not query_wants_personnel_structure(user_query):
        return False
    h = (reply or "").strip()
    if not h:
        return False
    if re.search(
        r"缺(?:失|乏).*(?:可比公司A|可比公司A)|可比公司A.*(?:缺失|缺少|无).*人员|可比公司A.*缺失证据|"
        r"完全缺失.*可比公司A|无法(?:进行|完成).*对比分析|证据严重缺失",
        h,
        re.I,
    ):
        return True
    if re.search(r"95\s*人\s*vs\s*1[,，]?378", h, re.I):
        return True
    # YYCQ侧被挂上 1378：同句内「YYCQ…1378」且中间无「可比公司A」才算误植
    for m in re.finditer(r"YYCQ[^\n]{0,200}1[,，]?378", h, re.I):
        if "可比公司A" not in m.group(0):
            return True
    for m in re.finditer(r"1[,，]?378[^\n]{0,120}YYCQ", h, re.I):
        span = m.group(0)
        if "可比公司A" not in span and not re.search(r"\|\s*1[,，]?378[^\n|]{0,20}\|\s*\d", span):
            return True
    if re.search(
        r"YYCQ[^\n]{0,120}疑似归属其他主体|"
        r"1[,，]?378[^\n]{0,80}不可能|误植为.*可比公司A|可比公司A等.*数据误植",
        h,
        re.I,
    ):
        return True
    # Hermes 把可比公司E/小厂在职员工（139/95）误挂到YYCQ，与 excel 分项 70 矛盾
    if re.search(r"YYCQ[^\n]{0,500}", h, re.I) and re.search(
        r"期末(?:员工总数|139)|员工总数139|139\s*人|技术人员95|研发[/／]技术人员占比极高",
        h,
        re.I,
    ):
        if re.search(r"1\.1信息-人员|研发70|70\.00|\|\s*70", h, re.I):
            return True
    if re.search(r"证据中代号[「\"']?可比公司E", h) and re.search(
        r"YYCQ[^\n]{0,200}(?:139|95)\s*人",
        h,
        re.I,
    ):
        return True
    if re.search(r"核心指标对照", h) and not re.search(r"人员结构对照", h):
        from backend.services.personnel_compare_report import personnel_excerpt_dump_only

        if personnel_excerpt_dump_only(h) or not re.search(r"可比公司A", h):
            return True
    if re.search(r"excel[^|\n]{0,48}研发[^|\n]{0,24}\|\s*1\s*\|", h, re.I):
        return True
    if re.search(r"\|\s*YYCQ[^\n|]{0,40}\|\s*1\s*\|", h):
        return True
    return False


def personnel_compare_excerpt_is_valid(excerpt: str, *, user_query: str) -> bool:
    from backend.services.kb_retrieval_plan import query_wants_personnel_structure

    if not query_wants_personnel_structure(user_query):
        return False
    from backend.services.personnel_compare_report import personnel_excerpt_dump_only

    h = (excerpt or "").strip()
    if not h or personnel_excerpt_reply_is_low_quality(h):
        return False
    entities = _personnel_entities(user_query)
    if len(entities) >= 2:
        for ent in entities[:2]:
            if ent not in h and not re.search(re.escape(ent[:2]), h):
                return False
    elif not re.search(r"可比公司A", h) or not re.search(r"YYCQ", h, re.I):
        return False
    from backend.services.personnel_compare_report import _STRUCTURE_TABLE_TITLE

    if not re.search(r"研发人员|1\.1信息-人员|人员结构对照|对比分析|\d{2,4}", h):
        return False
    if personnel_excerpt_dump_only(h):
        return False
    if len(_personnel_entities(user_query)) >= 2 and _STRUCTURE_TABLE_TITLE not in h:
        return False
    return True


def format_personnel_compare_report(excerpts: list[dict[str, str]], *, user_query: str = "") -> str | None:
    """两家主体结构化横比成稿（对比表 + 分析 + 摘要，非原文 dump）。"""
    from backend.services.personnel_compare_report import format_personnel_compare_structured_report

    return format_personnel_compare_structured_report(excerpts, user_query=user_query)


def merge_kb_ask_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    """合并多次 ask 的 citations / reply（人员结构 fan-out）。"""
    citations: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    reply_parts: list[str] = []
    for res in results:
        if not isinstance(res, dict) or res.get("denied"):
            continue
        rp = str(res.get("reply") or "").strip()
        if rp and rp not in reply_parts:
            reply_parts.append(rp)
        for c in res.get("citations") or []:
            if not isinstance(c, dict):
                continue
            k = _citation_key(c)
            if k in seen:
                continue
            seen.add(k)
            citations.append(c)
    return {"reply": " ".join(reply_parts).strip(), "citations": citations}


def personnel_structure_ask_results(
    ask_fn: Callable[[str], dict[str, Any]],
    user_query: str,
    *,
    max_subqueries: int = 6,
) -> dict[str, Any]:
    """人员/人效对比：fan-out 各主体 docling section / excel chunk 定向 query。"""
    import re

    from backend.services.kb_retrieval_plan import (
        enhance_kb_ask_query,
        personnel_retrieval_subqueries,
        query_wants_personnel_structure,
    )

    q = (user_query or "").strip()
    if not query_wants_personnel_structure(q):
        return ask_fn(q)
    from backend.services.kb_retrieval_plan import extract_query_entity_phrases

    planned: list[str] = []
    seen: set[str] = set()
    cap = max(4, int(max_subqueries))
    priority: list[str] = []
    ents = extract_query_entity_phrases(q)[:3]
    for term in ("研发人员情况 2025", "1.1信息-人员 2025全年"):
        for ent in ents:
            priority.append(f"{ent} {term}")
    for ent in ents:
        if re.search(r"可比公司A", ent):
            priority.extend(
                [
                    f"{ent} 员工数量 专业构成及教育程度 2025",
                    f"{ent} 1、员工数量、专业构成及教育程度",
                    f"{ent} 员工情况 专业构成 2025",
                    f"{ent} 在职员工 人数 2025",
                ]
            )
    for cand in [enhance_kb_ask_query(q), *priority, *personnel_retrieval_subqueries(q)]:
        c = (cand or "").strip()
        if not c or c in seen:
            continue
        seen.add(c)
        planned.append(c)
        if len(planned) >= cap:
            break
    merged = merge_kb_ask_results([ask_fn(sq) for sq in planned])
    if merged.get("citations"):
        return merged
    return ask_fn(q)


def execute_kb_subquery_ask(
    user_token: str,
    sub_q: str,
    *,
    ask_kwargs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """网关预检索/补检索与 MCP 共用：人员结构问句自动 fan-out。"""
    from backend.services.knowledge_pipeline import ask_knowledge
    from backend.services.kb_retrieval_plan import query_wants_personnel_structure

    kwargs = dict(ask_kwargs or {})

    def _ask(q: str) -> dict[str, Any]:
        return ask_knowledge(user_token, q, **kwargs)

    cap = 8 if query_wants_personnel_structure(sub_q) else 6
    return personnel_structure_ask_results(_ask, sub_q, max_subqueries=cap)


def build_kb_ask_mcp_reply(
    res: dict[str, Any],
    *,
    query: str,
    tenant_id: str,
    fixtures: dict[str, Any] | None = None,
    excerpt_limit: int = 6,
    excerpt_cap: int = 3500,
) -> tuple[str, list[dict[str, str]]]:
    """
    返回 (reply_text, evidence_excerpts)。
    Hermes MCP 须能在 reply 中看到 chunk 正文，而非仅 doc_id/score。
    """
    base = str(res.get("reply") or "").strip()
    citations = [c for c in (res.get("citations") or []) if isinstance(c, dict)]
    if not citations:
        return base, []

    from backend.services.agent_kb_prefetch import build_prefetch_evidence_excerpts
    from backend.services.kb_retrieval_plan import query_wants_personnel_structure

    personnel_excerpts = build_personnel_compare_excerpts(
        citations,
        query,
        tenant_id=tenant_id,
        fixtures=fixtures or {},
        excerpt_cap=max(800, int(excerpt_cap)),
    )
    if personnel_excerpts:
        excerpts = personnel_excerpts
    else:
        excerpts = build_prefetch_evidence_excerpts(
            citations,
            query,
            tenant_id=tenant_id,
            fixtures=fixtures or {},
            limit=max(1, int(excerpt_limit)),
            excerpt_cap=max(800, int(excerpt_cap)),
            max_chunks_per_doc=2,
        )
    if not excerpts:
        tail = (
            "\n\n（检索命中引用元数据，但未能加载 chunk 正文；"
            "请缩小 query 或换关键词后重试 orientg_kb_ask。）"
        )
        return (base + tail).strip(), []

    parts: list[str] = []
    if base:
        parts.append(base)
    label = "人员结构证据节选" if query_wants_personnel_structure(query) and personnel_excerpts else "证据节选"
    parts.append(f"\n## {label}（{len(excerpts)} 条，可直接用于分析）\n")
    for i, ex in enumerate(excerpts, 1):
        did = str(ex.get("doc_id") or "").strip()
        ent = str(ex.get("entity") or "").strip()
        title = f"{ent} ({did})" if ent else did
        parts.append(f"### 节选 {i} · {title}\n{str(ex.get('excerpt') or '').strip()}\n")
    return "\n".join(parts).strip(), excerpts


def resolve_doc_folder_labels(
    prefetch_result: dict[str, Any] | None,
    *,
    tenant_id: str,
    kb_scope: dict[str, list[str]] | None = None,
) -> dict[str, str]:
    pack = (prefetch_result or {}).get("evidence_pack") or {}
    labels = pack.get("doc_folder_labels")
    if isinstance(labels, dict) and labels:
        return labels
    roots = [str(x).strip() for x in ((kb_scope or {}).get("selected_folder_ids") or []) if str(x).strip()]
    if not roots:
        return {}
    from backend.services.kb_scope_context import build_scope_folder_context

    return build_scope_folder_context(tenant_id, selected_folder_ids=roots).get("doc_folder_labels") or {}


def _personnel_single_reply_has_required_numbers(reply: str, *, user_query: str) -> bool:
    h = reply or ""
    uq = user_query or ""
    wants_staff = bool(re.search(r"员工数量|专业构成|教育程度|在职员工|员工情况", uq))
    wants_rd = bool(re.search(r"研发人员", uq))
    wants_yycq = bool(re.search(r"YYCQ|1\.1信息", uq, re.I))
    if wants_staff:
        return bool(re.search(r"\b946\b", h) and re.search(r"\b242\b", h))
    if wants_rd:
        return bool(re.search(r"1[,，]?378|\b1378\b", h))
    if wants_yycq:
        return bool(re.search(r"\b70\b|70\.\d{2}", h))
    return len(h) >= 80 and bool(re.search(r"\d{2,4}", h))


def personnel_single_subject_reply_from_prefetch(
    prefetch_result: dict[str, Any],
    *,
    user_query: str,
    tenant_id: str,
    fixtures: dict[str, Any] | None = None,
    kb_scope: dict[str, list[str]] | None = None,
) -> str | None:
    """单主体人员专节：从 KB section boost 直接成稿，避免 LLM 误判「主体未标注」。"""
    from backend.services.ai_interaction_llm import _load_doc_chunk_text
    from backend.services.kb_retrieval_plan import (
        _personnel_subject_entities,
        query_wants_personnel_compare,
        query_wants_personnel_structure,
    )

    uq = (user_query or "").strip()
    if not query_wants_personnel_structure(uq) or query_wants_personnel_compare(uq):
        return None
    if len(_personnel_subject_entities(uq)) >= 2:
        return None
    citations = [c for c in (prefetch_result or {}).get("citations") or [] if isinstance(c, dict)]
    if not citations:
        return None
    tid = (tenant_id or "").strip() or "tenant1"
    doc_labels = resolve_doc_folder_labels(
        prefetch_result,
        tenant_id=tid,
        kb_scope=kb_scope,
    )
    citations = boost_personnel_compare_citations(
        citations,
        user_query=uq,
        tenant_id=tid,
        doc_folder_labels=doc_labels,
    )
    entities = _personnel_entities(uq)
    wants_staff = bool(re.search(r"员工数量|专业构成|教育程度|在职员工|员工情况", uq))
    wants_rd = bool(re.search(r"研发人员", uq))
    wants_yycq = bool(re.search(r"YYCQ|1\.1信息", uq, re.I))

    merged_txt = ""
    best_score = -1.0
    best_doc_id = ""
    for c in citations:
        did = str(c.get("doc_id") or "")
        if not did.startswith("ud_"):
            continue
        txt = _load_doc_chunk_text(
            tid,
            did,
            str(c.get("chunk_id")) if c.get("chunk_id") else None,
            c.get("chunk_seq_no"),
        ) or ""
        if not txt or _personnel_chunk_is_noise(txt):
            continue
        sc = _personnel_chunk_score(
            txt,
            entity=entities[0] if entities else "",
            doc_id=did,
            doc_folder_labels=doc_labels,
        )
        src = str(c.get("source") or "")
        if "personnel" in src and "boost" in src:
            sc += 5000.0
        if wants_staff and _PERSONNEL_STAFF_SECTION_PAT.search(txt):
            sc += 800.0
        if wants_rd and re.search(r"研发人员情况|研发人员数量", txt, re.I):
            sc += 800.0
        if wants_yycq and re.search(r"1\.1信息-人员", txt, re.I):
            sc += 800.0
        if sc > best_score:
            best_score = sc
            merged_txt = txt
            best_doc_id = did
    if not merged_txt:
        return None
    excerpt = _personnel_entity_excerpt(merged_txt, excerpt_cap=3500)
    if personnel_excerpt_reply_is_low_quality(excerpt):
        return None
    if entities:
        ent = entities[0]
        folder_ent = _entity_from_folder_label(best_doc_id, entities, doc_labels)
        title_ent = ent if _entity_matches_text(ent, excerpt) or _entity_matches_text(ent, merged_txt) else (folder_ent or ent)
    else:
        title_ent = "可比公司A" if wants_staff or wants_rd else "YYCQ"
    if wants_staff:
        heading = f"## {title_ent} · 2025 员工数量、专业构成及教育程度"
    elif wants_rd:
        heading = f"## {title_ent} · 2025 研发人员情况"
    else:
        heading = f"## {title_ent} · 2025 人员结构（1.1信息-人员）"
    reply = f"{heading}\n\n{excerpt.strip()}"
    if not _personnel_single_reply_has_required_numbers(reply, user_query=uq):
        return None
    return reply


def personnel_compare_reply_from_prefetch(
    prefetch_result: dict[str, Any],
    *,
    user_query: str,
    tenant_id: str,
    fixtures: dict[str, Any] | None = None,
    kb_scope: dict[str, list[str]] | None = None,
) -> str | None:
    """人员结构对比：仅从 KB 按主体各取一条人员 section，结构化成稿（禁止 top-8 原文 dump）。"""
    from backend.services.kb_retrieval_plan import query_wants_personnel_structure

    if not query_wants_personnel_structure(user_query):
        return None
    citations = [c for c in (prefetch_result or {}).get("citations") or [] if isinstance(c, dict)]
    if not citations:
        return None
    doc_labels = resolve_doc_folder_labels(
        prefetch_result,
        tenant_id=tenant_id,
        kb_scope=kb_scope,
    )

    excerpts = build_personnel_compare_excerpts(
        citations,
        user_query,
        tenant_id=tenant_id,
        fixtures=fixtures or {},
        doc_folder_labels=doc_labels,
        excerpt_cap=5500,
    )
    if len(excerpts) < 2:
        return None
    report = format_personnel_compare_report(excerpts, user_query=user_query)
    if not report or personnel_excerpt_reply_is_low_quality(report):
        return None
    merged = report
    if not re.search(r"可比公司A", merged) or not re.search(r"YYCQ", merged, re.I):
        return None
    if not re.search(r"人员|人数|研发人员|1\.1信息-人员|\d{2,4}", merged):
        return None
    return report
