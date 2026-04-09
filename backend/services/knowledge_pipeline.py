"""
2.d 落地：Knowledge 检索 Pipeline（pre-filter + citation + 最小可审计）。

当前版本目标：
- 不依赖向量库，先以“结构化过滤 + 关键词/模糊匹配”为主，保证链路可验收
- 保留可扩展点：后续可在同一接口中引入向量检索/重排（Hybrid）

安全约束：
- 不在返回中暴露不必要的明文证据（chunk_text）
- 上层审计只存 query hash 与证据 id 摘要
"""

from __future__ import annotations

import re
from typing import Any, Optional

from sqlalchemy import text

from backend.database import get_db
from backend.services.kb_acl_store import get_all_resource_assignments
from backend.services.knowledge_acl import compute_acl_scope, load_fixtures
from backend.services import kb_documents as kb_user_docs
from backend.services.kb_vector_store import search_doc_chunks, vector_enabled
from backend.services.kb_tables import retrieve_table_evidence


def _infer_intent(query: str) -> dict[str, bool]:
    q = (query or "").strip().lower()
    # 简化：默认需要 doc；命中明显“取数/表格”再加 table
    need_table = any(k in q for k in ["表", "数值", "金额", "净利润", "利润", "同比", "环比"])
    need_doc = True if q else False
    return {"need_doc": need_doc, "need_table": need_table}


def _normalize_query(q: str) -> str:
    s = (q or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s[:500]


def _load_doc_assignments(tenant_id: str) -> dict[str, set[str]]:
    m: dict[str, set[str]] = {}
    assigns = get_all_resource_assignments(tenant_id, resource_type="doc")
    for a in assigns:
        did = str(a.get("resource_id") or "").strip()
        cid = str(a.get("collection_id") or "").strip()
        if did and cid:
            m.setdefault(did, set()).add(cid)
    return m


def _load_table_assignments(tenant_id: str) -> dict[str, set[str]]:
    m: dict[str, set[str]] = {}
    assigns = get_all_resource_assignments(tenant_id, resource_type="table")
    for a in assigns:
        tid = str(a.get("resource_id") or "").strip()
        cid = str(a.get("collection_id") or "").strip()
        if tid and cid:
            m.setdefault(tid, set()).add(cid)
    return m


def _candidate_doc_ids(
    *,
    allowed_doc_ids: set[str],
    selected_collection_ids: set[str],
    doc_assignments: dict[str, set[str]],
) -> set[str]:
    if not allowed_doc_ids:
        return set()
    if not selected_collection_ids:
        return set(allowed_doc_ids)
    out: set[str] = set()
    for did in allowed_doc_ids:
        cids = doc_assignments.get(str(did), set())
        if cids.intersection(selected_collection_ids):
            out.add(str(did))
    return out


def _retrieve_uploaded_doc_chunks(
    tenant_id: str,
    *,
    doc_ids: set[str],
    query: str,
    limit: int = 6,
) -> list[dict[str, Any]]:
    """
    从 PG 的 kb_user_document_chunks 做最小检索（ILIKE）。
    注意：这里只覆盖 ud_* 上传文档；fixtures 文档走另一条路径。
    """
    ud_ids = sorted([d for d in doc_ids if str(d).startswith("ud_")])
    if not ud_ids:
        return []
    q = _normalize_query(query)
    if not q:
        return []
    pattern = f"%{q}%"
    with get_db() as db:
        rows = db.execute(
            text(
                """
                SELECT c.doc_id, c.chunk_id, c.chunk_seq_no
                FROM kb_user_document_chunks c
                WHERE c.doc_id = ANY(:doc_ids)
                  AND c.chunk_text ILIKE :pat
                ORDER BY c.doc_id, c.chunk_seq_no
                LIMIT :lim
                """
            ),
            {"doc_ids": ud_ids, "pat": pattern, "lim": max(1, min(30, int(limit)))},
        ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "evidence_type": "doc_chunk",
                "doc_id": str(r[0]),
                "section_id": None,
                "chunk_id": str(r[1]),
                "chunk_seq_no": int(r[2] or 0),
            }
        )
    return out


def _retrieve_fixture_doc_chunks(
    documents: list[dict[str, Any]],
    *,
    doc_ids: set[str],
    selected_collection_ids: set[str],
    doc_assignments: dict[str, set[str]],
    query: str,
    limit: int = 3,
) -> list[dict[str, Any]]:
    q = _normalize_query(query).lower()
    if not q:
        return []
    out: list[dict[str, Any]] = []
    for d in documents:
        did = str(d.get("doc_id") or "").strip()
        if not did or did not in doc_ids:
            continue
        cids = doc_assignments.get(did, set())
        hit_cids = sorted([cid for cid in cids if (not selected_collection_ids) or (cid in selected_collection_ids)])
        if not hit_cids:
            continue
        chosen_cid = hit_cids[0]
        title = str(d.get("title") or "").lower()
        for s in d.get("sections") or []:
            keywords = [str(x).lower() for x in (s.get("keywords") or [])]
            sec_text = str(s.get("text") or "").lower()
            hit = (q in title) or (q and q in sec_text) or any(kw in q for kw in keywords)
            for ch in s.get("chunks") or []:
                ch_text = str(ch.get("text") or "").lower()
                if hit or (q and q in ch_text) or any(kw in ch_text for kw in keywords):
                    out.append(
                        {
                            "evidence_type": "doc_chunk",
                            "doc_id": did,
                            "collection_id": chosen_cid,
                            "section_id": s.get("section_id"),
                            "chunk_id": ch.get("chunk_id"),
                            "chunk_seq_no": ch.get("chunk_seq_no"),
                        }
                    )
        if len(out) >= limit:
            break
    # 去重
    seen = set()
    dedup: list[dict[str, Any]] = []
    for e in out:
        k = (e.get("doc_id"), e.get("chunk_id"))
        if k in seen:
            continue
        seen.add(k)
        dedup.append(e)
    return dedup[: max(1, int(limit))]


def _pick_collection_id_for_doc(
    doc_id: str,
    *,
    doc_assignments: dict[str, set[str]],
    selected_collection_ids: set[str],
) -> str | None:
    cids = doc_assignments.get(str(doc_id), set())
    if not cids:
        return None
    if selected_collection_ids:
        cand = sorted([c for c in cids if c in selected_collection_ids])
        if cand:
            return cand[0]
    return sorted(cids)[0]


def _table_retrieve_from_fixtures(
    fixtures: dict[str, Any],
    *,
    selected_table_ids: set[str],
    query: str,
    table_assignments: dict[str, set[str]],
    allowed_collection_ids: set[str],
) -> dict[str, Any]:
    q = _normalize_query(query).lower()
    for t in fixtures.get("tables") or []:
        if t.get("table_id") not in selected_table_ids:
            continue
        table_id = str(t.get("table_id") or "").strip()
        if not table_id:
            continue
        table_cids = table_assignments.get(table_id, set())
        cid_allowed = sorted([cid for cid in table_cids if cid in allowed_collection_ids])
        if not cid_allowed:
            continue
        columns = t.get("columns") or []
        rows = t.get("rows") or []
        target_row = None
        for r in rows:
            row_keywords = [str(x).lower() for x in (r.get("keywords") or [])]
            if any(kw in q for kw in row_keywords):
                target_row = r
                break
        if not target_row and rows:
            target_row = rows[0]
        if not target_row:
            continue
        values = target_row.get("values") or {}
        column_id: Optional[str] = None
        for c in columns:
            cid = c.get("column_id")
            if cid and cid in values and isinstance(values.get(cid), (int, float)):
                column_id = cid
                break
        if not column_id:
            for k in values.keys():
                column_id = str(k)
                break
        return {
            "evidence": {
                "evidence_type": "table_row",
                "table_id": table_id,
                "collection_id": cid_allowed[0],
                "row_key": target_row.get("row_key"),
                "column_id": column_id,
            },
            "answer_value": values.get(column_id) if column_id else None,
        }
    return {"evidence": None, "answer_value": None}


def ask_knowledge(
    user_token: str,
    query: str,
    *,
    selected_collection_ids: Optional[list[str]] = None,
    selected_table_ids: Optional[list[str]] = None,
    fixtures: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    fixtures = fixtures or load_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    q = _normalize_query(query)
    if not q:
        return {"denied": True, "deny_reason": "empty query", "citations": []}

    scope = compute_acl_scope(user_token, fixtures=fixtures)
    allowed_collection_ids = set(scope["allowed_collection_ids"])
    allowed_doc_ids = set(scope["allowed_doc_ids"])
    allowed_table_ids = set(scope["allowed_table_ids"])

    selected_collection_ids_set = set(selected_collection_ids or [])
    selected_table_ids_set = set(selected_table_ids or [])

    # 子集校验（pre-filter 必选）
    if selected_collection_ids is not None and not selected_collection_ids_set.issubset(allowed_collection_ids):
        return {"denied": True, "deny_reason": "selected_collection_ids not allowed", "citations": []}
    if selected_table_ids is not None and not selected_table_ids_set.issubset(allowed_table_ids):
        return {"denied": True, "deny_reason": "selected_table_ids not allowed", "citations": []}

    intent = _infer_intent(q)

    # 默认选择：按意图启用
    if intent["need_doc"] and not selected_collection_ids_set:
        selected_collection_ids_set = set(allowed_collection_ids)
    if intent["need_table"] and not selected_table_ids_set:
        selected_table_ids_set = set(allowed_table_ids)

    # empty scope deny（按意图所需证据类型）
    if intent["need_doc"] and (not allowed_doc_ids or not selected_collection_ids_set):
        return {"denied": True, "deny_reason": "doc allowed scope empty", "citations": []}
    if intent["need_table"] and (not allowed_table_ids or not selected_table_ids_set):
        return {"denied": True, "deny_reason": "table allowed scope empty", "citations": []}

    doc_assignments = _load_doc_assignments(tenant_id)
    table_assignments = _load_table_assignments(tenant_id)

    cand_doc_ids = _candidate_doc_ids(
        allowed_doc_ids=allowed_doc_ids,
        selected_collection_ids=selected_collection_ids_set,
        doc_assignments=doc_assignments,
    )

    citations: list[dict[str, Any]] = []
    reply_parts: list[str] = []
    used_vector = False
    used_keyword = False

    # 文档检索（Hybrid 的 keyword 部分，先落地）
    if intent["need_doc"]:
        # fixtures 文档 + 用户上传文档（作为 fixture documents 参与统一检索）
        merged_documents = list(fixtures.get("documents") or [])
        try:
            extra_docs = kb_user_docs.load_user_docs_as_fixture_documents(tenant_id, cand_doc_ids)
            merged_documents.extend(extra_docs)
        except Exception:
            pass

        # 1) 向量召回（若可用）：只在候选 doc 范围内检索，天然 pre-filter
        if vector_enabled():
            try:
                vec_hits = search_doc_chunks(
                    tenant_id,
                    query=q,
                    candidate_doc_ids=sorted(cand_doc_ids),
                    k=6,
                )
            except Exception:
                vec_hits = []
            for h in vec_hits:
                used_vector = True
                did = str(h.get("doc_id"))
                cid = _pick_collection_id_for_doc(
                    did,
                    doc_assignments=doc_assignments,
                    selected_collection_ids=selected_collection_ids_set,
                )
                citations.append(
                    {
                        "evidence_type": "doc_chunk",
                        "doc_id": did,
                        "collection_id": cid,
                        "section_id": None,
                        "chunk_id": h.get("chunk_id"),
                        "chunk_seq_no": h.get("chunk_seq_no"),
                        "score": h.get("score"),
                    }
                )

        # 2) keyword 兜底：uploaded chunks（PG ILIKE）
        uploaded_hits = _retrieve_uploaded_doc_chunks(tenant_id, doc_ids=cand_doc_ids, query=q, limit=6)
        for h in uploaded_hits:
            used_keyword = True
            did = str(h.get("doc_id"))
            cid = _pick_collection_id_for_doc(
                did,
                doc_assignments=doc_assignments,
                selected_collection_ids=selected_collection_ids_set,
            )
            citations.append(
                {
                    "evidence_type": "doc_chunk",
                    "doc_id": did,
                    "collection_id": cid,
                    "section_id": h.get("section_id"),
                    "chunk_id": h.get("chunk_id"),
                    "chunk_seq_no": h.get("chunk_seq_no"),
                }
            )

        # 2) fixtures chunks（内存）
        fixture_hits = _retrieve_fixture_doc_chunks(
            merged_documents,
            doc_ids=cand_doc_ids,
            selected_collection_ids=selected_collection_ids_set,
            doc_assignments=doc_assignments,
            query=q,
            limit=3,
        )
        for h in fixture_hits:
            used_keyword = True
            citations.append(
                {
                    "evidence_type": "doc_chunk",
                    "doc_id": h.get("doc_id"),
                    "collection_id": h.get("collection_id"),
                    "section_id": h.get("section_id"),
                    "chunk_id": h.get("chunk_id"),
                    "chunk_seq_no": h.get("chunk_seq_no"),
                }
            )

        # 去重（doc_id+chunk_id+table_id+row_key 维度）
        seen_keys = set()
        dedup_citations: list[dict[str, Any]] = []
        for c in citations:
            k = (
                str(c.get("doc_id") or ""),
                str(c.get("chunk_id") or ""),
                str(c.get("table_id") or ""),
                str(c.get("row_key") or ""),
                str(c.get("column_id") or ""),
            )
            if k in seen_keys:
                continue
            seen_keys.add(k)
            dedup_citations.append(c)
        citations = dedup_citations[:10]

        if citations:
            reply_parts.append(f"已在权限范围内匹配到文档证据（{len([c for c in citations if c.get('doc_id')])} 条）。")
        else:
            reply_parts.append("在当前权限范围内未找到匹配的文档证据。")

    # 表格检索（沿用 fixtures 模拟，保证 table citation 可验收）
    if intent["need_table"]:
        # 2.d：table content QA 必须在 allowed_table_ids 上做 pre-filter
        selected_allowed_table_ids = set([x for x in selected_table_ids_set if x in allowed_table_ids])

        # 1) 先尝试 DB TableInstance（持久化表）
        table_res = {"evidence": None, "answer_value": None}
        try:
            table_res = retrieve_table_evidence(
                tenant_id,
                selected_table_ids=selected_allowed_table_ids,
                query=q,
            )
        except Exception:
            table_res = {"evidence": None, "answer_value": None}

        # 2) 回退 fixtures（演示表/兼容）
        if not table_res.get("evidence"):
            table_res = _table_retrieve_from_fixtures(
                fixtures,
                selected_table_ids=selected_allowed_table_ids,
                query=q,
                table_assignments=table_assignments,
                allowed_collection_ids=allowed_collection_ids,
            )
        evidence = table_res.get("evidence")
        if evidence:
            citations.append(evidence)
            reply_parts.append(f"表格证据已匹配：{table_res.get('answer_value')}。")
        else:
            reply_parts.append("在当前权限范围内未找到匹配的表格证据。")

    if not reply_parts:
        return {"denied": True, "deny_reason": "unknown intent", "citations": []}
    if used_vector and used_keyword:
        mode = "mixed"
    elif used_vector:
        mode = "vector"
    else:
        mode = "keyword"

    return {"denied": False, "reply": " ".join(reply_parts), "citations": citations, "retrieval_mode": mode}

