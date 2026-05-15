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
    # 简化：默认需要 doc；命中明显"取数/表格"再加 table
    need_table = any(k in q for k in ["表", "数值", "金额", "净利润", "利润", "同比", "环比"])
    need_doc = True if q else False
    return {"need_doc": need_doc, "need_table": need_table}


def _normalize_query(q: str) -> str:
    s = (q or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s[:500]


def _tokenize_query(q: str) -> list[str]:
    """将查询切分为有意义的检索词条（jieba 分词，取长度 ≥2 的去重词）"""
    terms: list[str] = []
    try:
        import jieba
    except ImportError:
        # 无 jieba：按空格/标点简单切分，取长度 ≥2 的词
        raw = re.split(r"[\s,，。！？、；：""''（）\(\)【】\[\]{}]+", q)
        terms = [t.strip() for t in raw if len(t.strip()) >= 2]
        return list(dict.fromkeys(terms))  # 去重保序

    words = jieba.cut(q)
    for w in words:
        w = w.strip()
        if len(w) >= 2 and re.search(r"[\w\u4e00-\u9fff]", w):
            terms.append(w)
    return list(dict.fromkeys(terms))  # 去重保序


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


def _prepare_citations_chunk(
    item: dict[str, Any],
    doc_assignments: dict[str, set[str]],
    selected_collection_ids: set[str],
) -> dict[str, Any]:
    """将混合检索条目转为统一的 citation 格式"""
    did = str(item.get("doc_id") or "")
    cid = _pick_collection_id_for_doc(did, doc_assignments=doc_assignments, selected_collection_ids=selected_collection_ids)
    return {
        "evidence_type": "doc_chunk",
        "doc_id": did,
        "collection_id": cid,
        "section_id": None,
        "chunk_id": item.get("chunk_id"),
        "chunk_seq_no": item.get("chunk_seq_no"),
        "score": item.get("hybrid_score"),
    }


def _hybrid_retrieve(
    tenant_id: str,
    query: str,
    candidate_doc_ids: set[str],
    *,
    k: int = 20,
) -> list[dict[str, Any]]:
    """
    混合检索：向量语义搜索 + 关键词精确匹配 → 加权综合评分 + 上下文 re-rank。

    策略：
    - 向量命中：余弦相似度转 0~1 分数，基础权重 0.6
    - 关键词命中：多词 OR 匹配 + 词频加权，基础权重 0.4
    - 双命中：0.6×向量 + 0.4×关键词
    - 上下文 re-rank：同文档相邻 chunk 互相 boost（前一个高分 → 后一个 +15%）
    """
    doc_ids_list = sorted(candidate_doc_ids)

    # 1) 向量检索
    vec_hits: list[dict[str, Any]] = []
    if vector_enabled():
        try:
            vec_hits = search_doc_chunks(tenant_id, query=query, candidate_doc_ids=doc_ids_list, k=k * 2)
        except Exception:
            pass

    # 2) 关键词检索（已增强：jieba 分词 + 词频加权）
    kw_hits = _retrieve_uploaded_doc_chunks(tenant_id, doc_ids=candidate_doc_ids, query=query, limit=k * 2)

    # 3) 合并去重：key = (doc_id, chunk_id)
    combined: dict[tuple[str, str], dict[str, Any]] = {}

    # 向量 → 余弦距离转为相似度 (0~1)
    for h in vec_hits:
        key = (str(h.get("doc_id") or ""), str(h.get("chunk_id") or ""))
        dist = float(h.get("score") or 0)
        sim = 1.0 / (1.0 + dist) if dist >= 0 else 0.5
        combined[key] = {**h, "vec_sim": sim, "kw_pos": 0, "hybrid_score": 0}

    # 关键词 → 位置越靠前分数越高
    for i, h in enumerate(kw_hits):
        key = (str(h.get("doc_id") or ""), str(h.get("chunk_id") or ""))
        pos_score = 1.0 - (i / max(len(kw_hits), 1)) * 0.3
        if key in combined:
            combined[key]["kw_pos"] = pos_score
        else:
            combined[key] = {**h, "vec_sim": 0, "kw_pos": pos_score, "hybrid_score": 0}

    # 4) 混合评分
    for key, info in combined.items():
        v = info["vec_sim"]
        kw = info["kw_pos"]
        if v > 0 and kw > 0:
            info["hybrid_score"] = 0.6 * v + 0.4 * kw
        elif v > 0:
            info["hybrid_score"] = v * 0.75  # 纯向量：轻微降权
        else:
            info["hybrid_score"] = kw * 0.5  # 纯关键词：较大降权

    # 5) 上下文 re-rank：同文档相邻 chunk 互相正向 boost
    by_doc: dict[str, list[dict[str, Any]]] = {}
    for info in combined.values():
        did = str(info.get("doc_id") or "")
        by_doc.setdefault(did, []).append(info)

    for did, items in by_doc.items():
        items.sort(key=lambda x: int(x.get("chunk_seq_no") or 0))
        for i in range(len(items)):
            # 左邻 boost
            if i > 0 and items[i - 1]["hybrid_score"] > 0.25:
                items[i]["hybrid_score"] = min(1.0, items[i]["hybrid_score"] + items[i - 1]["hybrid_score"] * 0.12)
            # 右邻 boost
            if i < len(items) - 1 and items[i + 1]["hybrid_score"] > 0.25:
                items[i]["hybrid_score"] = min(1.0, items[i]["hybrid_score"] + items[i + 1]["hybrid_score"] * 0.12)

    # 6) 排序 + top-K
    all_items = list(combined.values())
    all_items.sort(key=lambda x: -x["hybrid_score"])
    return all_items[:k]


def _retrieve_uploaded_doc_chunks(
    tenant_id: str,
    *,
    doc_ids: set[str],
    query: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """
    增强关键词检索：先用 jieba 分词提取检索词条，再用 PG ILIKE 做多词 OR 匹配，
    最后在 Python 侧按词频 + 标题命中加权评分，返回 top-K。
    兜底：无 jieba 时按空格切分 + ILIKE OR。
    """
    ud_ids = sorted([d for d in doc_ids if str(d).startswith("ud_")])
    if not ud_ids:
        return []
    q = _normalize_query(query)
    if not q:
        return []
    terms = _tokenize_query(q)
    if not terms:
        terms = [q[:80]]  # 兜底：用原始查询前 80 字符

    # 构建 OR ILIKE 条件：每个词条一个 ILIKE
    or_clauses = " OR ".join([f"c.chunk_text ILIKE :t{i}" for i in range(len(terms))])
    params: dict[str, Any] = {"doc_ids": ud_ids, "lim": max(limit * 3, 60)}  # 多取一些再排序
    for i, t in enumerate(terms):
        params[f"t{i}"] = f"%{t[:80]}%"

    sql = f"""
        SELECT c.doc_id, c.chunk_id, c.chunk_seq_no, c.chunk_text
        FROM kb_user_document_chunks c
        WHERE c.doc_id = ANY(:doc_ids)
          AND ({or_clauses})
        ORDER BY c.doc_id, c.chunk_seq_no
        LIMIT :lim
    """

    with get_db() as db:
        rows = db.execute(text(sql), params).fetchall()

    # 评分：词频 + 标题加权
    scored: list[tuple[int, str, str, str, int]] = []  # (score, doc_id, chunk_id, chunk_text, seq_no)
    for r in rows:
        did = str(r[0])
        chid = str(r[1])
        seq = int(r[2] or 0)
        txt = str(r[3] or "").lower()
        score = 0
        for t in terms:
            t_lower = t.lower()
            count = txt.count(t_lower)
            score += count * 3  # 正文命中：每词 3 分
            # 标题命中加权（chunk_text 以 "## " 开头表示标题行）
            if txt.strip().startswith("## ") or txt.strip().startswith("# "):
                if t_lower in txt.split("\n")[0].lower():
                    score += 15  # 标题行命中加 15 分
        if score > 0:
            scored.append((score, did, chid, seq))

    scored.sort(key=lambda x: -x[0])
    top = scored[:limit]

    out: list[dict[str, Any]] = []
    for score, did, chid, seq in top:
        out.append(
            {
                "evidence_type": "doc_chunk",
                "doc_id": did,
                "section_id": None,
                "chunk_id": chid,
                "chunk_seq_no": seq,
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
    attached_doc_ids: Optional[list[str]] = None,
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

    # 处理 attached_doc_ids：从 composerAttachments 带入的文档引用
    # 1) ACL 过滤 + 解析所属 collection → 自动设定 RAG 范围（用户未显式选择时）
    # 2) 始终将附带文档加入候选检索范围（并在后续检索中优先）
    attached_doc_ids_set = allowed_doc_ids & set(attached_doc_ids or [])
    if attached_doc_ids_set:
        doc_assignments_att = _load_doc_assignments(tenant_id)
        attached_collections = set()
        for did in attached_doc_ids_set:
            attached_collections.update(doc_assignments_att.get(did, set()))
        if attached_collections and not selected_collection_ids_set:
            # 用户未显式选范围 → 以附带文档的 collection 作为 RAG 范围
            selected_collection_ids_set = attached_collections

    intent = _infer_intent(q)

    # 默认选择：按意图启用
    if intent["need_doc"] and not selected_collection_ids_set:
        selected_collection_ids_set = set(allowed_collection_ids)
    if intent["need_table"] and not selected_table_ids_set:
        selected_table_ids_set = set(allowed_table_ids)

    # empty scope deny（按意图所需证据类型；有附带文档时不因 scope 为空而拒绝）
    has_attached = bool(attached_doc_ids_set)
    if intent["need_doc"] and (not allowed_doc_ids or not selected_collection_ids_set) and not has_attached:
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

    # 始终将附带文档加入候选检索范围（即使它不在选定的 collection 中）
    if attached_doc_ids_set:
        cand_doc_ids = cand_doc_ids | attached_doc_ids_set

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

        # 混合检索：向量（语义）+ 关键词（精确）→ 加权综合 + 上下文 re-rank
        hybrid_hits = _hybrid_retrieve(tenant_id, query=q, candidate_doc_ids=cand_doc_ids, k=20)
        if hybrid_hits:
            used_vector = any(h.get("hybrid_score", 0) > 0 and h.get("vec_sim", 0) > 0 for h in hybrid_hits)
            used_keyword = any(h.get("hybrid_score", 0) > 0 and h.get("kw_pos", 0) > 0 for h in hybrid_hits)
            for h in hybrid_hits:
                citations.append(
                    _prepare_citations_chunk(h, doc_assignments=doc_assignments, selected_collection_ids=selected_collection_ids_set)
                )
            reply_parts.append(f"混合检索命中 {len(hybrid_hits)} 条证据"
                               f"{'（向量+关键词）' if used_vector and used_keyword else '（纯向量）' if used_vector else '（纯关键词）'}。")

        # fixtures chunks（内存，不受向量/关键词影响）
        fixture_hits = _retrieve_fixture_doc_chunks(
            merged_documents,
            doc_ids=cand_doc_ids,
            selected_collection_ids=selected_collection_ids_set,
            doc_assignments=doc_assignments,
            query=q,
            limit=10,
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
        citations = dedup_citations[:30]

        # 常规检索无结果 + 用户明确带了文档 → 全文回退：取附带文档的全部 chunk
        if not citations and attached_doc_ids_set:
            ud_ids = sorted([d for d in attached_doc_ids_set if str(d).startswith("ud_")])
            if ud_ids:
                try:
                    with get_db() as db:
                        rows = db.execute(
                            text(
                                """
                                SELECT c.doc_id, c.chunk_id, c.chunk_seq_no
                                FROM kb_user_document_chunks c
                                WHERE c.doc_id = ANY(:doc_ids)
                                ORDER BY c.doc_id, c.chunk_seq_no
                                LIMIT :lim
                                """
                            ),
                            {"doc_ids": ud_ids, "lim": 10},
                        ).fetchall()
                    for r in rows:
                        did = str(r[0])
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
                                "chunk_id": str(r[1]),
                                "chunk_seq_no": int(r[2] or 0),
                            }
                        )
                    if citations:
                        used_keyword = True
                        reply_parts.append(f"已加载附带文档证据（全文回退，{len(citations)} 条片段）。")
                except Exception:
                    pass

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

