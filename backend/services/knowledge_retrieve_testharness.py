"""
Knowledge 检索验收测试桩（test harness）

目的：在没有向量库/真实 RAG 的情况下，
让你能端到端验收 2.b 的 ACL scope + deny + citation 关键链路。

当前实现：
- 使用 fixture 中的 doc/chunk 文本关键词匹配来“模拟检索”
- 使用 fixture 的表实例 rows/values 来“模拟数值问答”
- citation 必须包含定位字段（doc/chunk 或 table/row），并在权限允许范围内返回
"""

from __future__ import annotations

from typing import Any, Optional

from backend.services.knowledge_acl import compute_acl_scope, load_fixtures
from backend.services.kb_acl_store import get_all_resource_assignments
from backend.services import kb_documents as kb_user_docs


def _infer_intent(query: str) -> dict[str, bool]:
    q = (query or "").strip().lower()
    need_doc = any(k in q for k in ["规章", "制度", "流程", "审批", "报销", "审核", "归档", "口径", "文档", "上传", "总结", "内容"])
    need_table = any(k in q for k in ["利润", "净利润", "本年累计", "表", "数值", "金额"])
    if not need_doc and not need_table and len(q) > 0:
        need_doc = True
    return {"need_doc": need_doc, "need_table": need_table}


def _doc_retrieve(
    documents: list[dict[str, Any]],
    *,
    selected_collection_ids: set[str],
    doc_assignments: dict[str, set[str]],
    query: str,
) -> list[dict[str, Any]]:
    q = (query or "").strip().lower()
    out: list[dict[str, Any]] = []
    for d in documents:
        doc_id = d.get("doc_id")
        doc_cids = doc_assignments.get(str(doc_id), set())
        hit_cids = [cid for cid in doc_cids if cid in selected_collection_ids]
        if not hit_cids:
            continue
        # 在该 doc 的 chunk 中找关键词命中
        chosen_cid = sorted(hit_cids)[0]
        for s in d.get("sections") or []:
            keywords = [str(x).lower() for x in (s.get("keywords") or [])]
            # 命中逻辑：关键词命中 / 标题命中 / section_text 包含命中
            hit = (
                any(kw in q for kw in keywords)
                or any(kw in q for kw in [d.get("title") or ""])
                or (str(s.get("text") or "").lower().find(q) >= 0)
            )
            for ch in s.get("chunks") or []:
                ch_text = str(ch.get("text") or "").lower()
                if hit or any(kw in ch_text for kw in keywords) or (q and q in ch_text):
                    out.append(
                        {
                            "evidence_type": "doc_chunk",
                            "doc_id": doc_id,
                            "collection_id": chosen_cid,
                            "section_id": s.get("section_id"),
                            "chunk_id": ch.get("chunk_id"),
                            "chunk_seq_no": ch.get("chunk_seq_no"),
                            "chunk_text": ch.get("text"),
                        }
                    )
    # 去重并限制条数
    seen = set()
    dedup: list[dict[str, Any]] = []
    for e in out:
        k = (e.get("doc_id"), e.get("chunk_id"))
        if k in seen:
            continue
        seen.add(k)
        dedup.append(e)
    return dedup[:3]


def _table_retrieve(
    fixtures: dict[str, Any],
    *,
    selected_table_ids: set[str],
    query: str,
    table_assignments: dict[str, set[str]],
    allowed_collection_ids: set[str],
) -> dict[str, Any]:
    """
    返回：
    - evidence: table_row citation（带 table_id/row_key/column_id）
    - answer_value: 计算/取值结果（用于 reply）
    """
    q = (query or "").strip().lower()
    # 简化规则：
    # - 命中 row：只要 query 包含 row.keywords 任一命中即可
    # - answer_value：优先取数值型列（col_amount 或最先 value）
    for t in fixtures.get("tables") or []:
        if t.get("table_id") not in selected_table_ids:
            continue
        table_id = str(t.get("table_id"))
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
            # 如果没有关键词命中，兜底取第一行（用于验收）
            target_row = rows[0]
        if not target_row:
            continue

        row_key = target_row.get("row_key")
        values = target_row.get("values") or {}

        # 选择一个“最可能的值列”
        column_id: Optional[str] = None
        for c in columns:
            cid = c.get("column_id")
            if cid and cid in values:
                # 取数值优先
                v = values.get(cid)
                if isinstance(v, (int, float)):
                    column_id = cid
                    break
        if not column_id:
            # 如果没有显式数值列，取第一个存在的列
            for k in values.keys():
                column_id = k
                break

        answer_value = values.get(column_id) if column_id else None
        return {
            "evidence": {
                "evidence_type": "table_row",
                "table_id": t.get("table_id"),
                "collection_id": cid_allowed[0],
                "row_key": row_key,
                "column_id": column_id,
            },
            "answer_value": answer_value,
        }

    return {"evidence": None, "answer_value": None}


def ask_knowledge_testharness(
    user_token: str,
    query: str,
    *,
    selected_collection_ids: Optional[list[str]] = None,
    selected_table_ids: Optional[list[str]] = None,
    fixtures: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    fixtures = fixtures or load_fixtures()
    scope = compute_acl_scope(user_token, fixtures=fixtures)

    allowed_collection_ids = set(scope["allowed_collection_ids"])
    allowed_table_ids = set(scope["allowed_table_ids"])
    tenant_id = fixtures.get("tenant_id") or "tenant1"

    # DB 的 resource->collection 分配用于 citation collection_id 的一致性
    doc_assignments: dict[str, set[str]] = {}
    table_assignments: dict[str, set[str]] = {}
    try:
        doc_assigns = get_all_resource_assignments(tenant_id, resource_type="doc")
        for a in doc_assigns:
            doc_assignments.setdefault(str(a.get("resource_id")), set()).add(str(a.get("collection_id")))
        table_assigns = get_all_resource_assignments(tenant_id, resource_type="table")
        for a in table_assigns:
            table_assignments.setdefault(str(a.get("resource_id")), set()).add(str(a.get("collection_id")))
    except Exception:
        # DB 不可用则回退 fixtures 的静态归属
        for d in fixtures.get("documents") or []:
            did = str(d.get("doc_id"))
            for cid in d.get("collection_ids") or []:
                doc_assignments.setdefault(did, set()).add(str(cid))
        for t in fixtures.get("tables") or []:
            tid = str(t.get("table_id"))
            cid = t.get("collection_id")
            if tid and cid:
                table_assignments.setdefault(tid, set()).add(str(cid))

    intent = _infer_intent(query)

    ud_ids = {str(k) for k in doc_assignments if str(k).startswith("ud_")}
    extra_docs = kb_user_docs.load_user_docs_as_fixture_documents(tenant_id, ud_ids)
    merged_documents: list[dict[str, Any]] = list(fixtures.get("documents") or []) + extra_docs

    # 校验 selected 子集
    selected_collection_ids_set = set(selected_collection_ids or [])
    selected_table_ids_set = set(selected_table_ids or [])

    if selected_collection_ids is not None:
        if not selected_collection_ids_set.issubset(allowed_collection_ids):
            return {"denied": True, "deny_reason": "selected_collection_ids not allowed", "citations": []}

    if selected_table_ids is not None:
        if not selected_table_ids_set.issubset(allowed_table_ids):
            return {"denied": True, "deny_reason": "selected_table_ids not allowed", "citations": []}

    # 若未显式选择，则给默认选择：按意图选择可访问资源
    if not selected_collection_ids_set and intent["need_doc"]:
        # doc 只需要 allowed collections 即可（因为 doc chunk 会在 those collections 内检索）
        selected_collection_ids_set = allowed_collection_ids
    if not selected_table_ids_set and intent["need_table"]:
        selected_table_ids_set = allowed_table_ids

    # 空 scope 行为：对“意图所需证据类型”必须 deny
    if intent["need_doc"] and not selected_collection_ids_set:
        return {"denied": True, "deny_reason": "doc allowed scope empty", "citations": []}
    if intent["need_table"] and not selected_table_ids_set:
        return {"denied": True, "deny_reason": "table allowed scope empty", "citations": []}

    citations: list[dict[str, Any]] = []
    reply_parts: list[str] = []

    # doc
    if intent["need_doc"]:
        doc_hits = _doc_retrieve(
            merged_documents,
            selected_collection_ids=selected_collection_ids_set,
            doc_assignments=doc_assignments,
            query=query,
        )
        if not doc_hits:
            # allowed scope 不是空，但检索命中不到：仍返回安全提示（验收可观测）
            reply_parts.append("在当前权限范围内未找到匹配的文档证据。")
        else:
            # citation 里不要返回 chunk_text 原文（审计不得记录敏感明文）
            for h in doc_hits:
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
            reply_parts.append(f"文档证据已匹配（共 {len(doc_hits)} 条）。")

    # table
    if intent["need_table"]:
        table_res = _table_retrieve(
            fixtures,
            selected_table_ids=selected_table_ids_set,
            query=query,
            table_assignments=table_assignments,
            allowed_collection_ids=allowed_collection_ids,
        )
        evidence = table_res.get("evidence")
        if not evidence:
            reply_parts.append("在当前权限范围内未找到匹配的表格证据。")
        else:
            citations.append(evidence)
            answer_value = table_res.get("answer_value")
            reply_parts.append(f"表格证据已匹配：{answer_value}。")

    if not reply_parts:
        # 没有意图命中：安全返回
        return {"denied": True, "deny_reason": "unknown intent (no doc/table)", "citations": []}

    return {
        "denied": False,
        "reply": " ".join(reply_parts),
        "citations": citations,
    }

