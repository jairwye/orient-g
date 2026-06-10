"""Agent 网关：KB 预检索 + 与 AI 互动同款的 LLM 证据综合（默认），可选再走 Hermes。"""

from __future__ import annotations

import json
import re
from typing import Any

from backend.config import settings
from backend.services import orientg_mcp_tools as mcp_tools
from backend.services.agent_kb_fast_path import prefetch_has_usable_evidence
from backend.services.kb_scope_resolve import resolve_kb_scope_for_ask
from backend.services.knowledge_acl import load_fixtures


def _citation_base_score(c: dict[str, Any], index: int) -> float:
    """统一 citation.score：None 用检索序位；0~1 视为相似度；其余为 pipeline 原始分。"""
    sc = c.get("score")
    if sc is None:
        return max(0.0, 1000.0 - float(index))
    try:
        v = float(sc)
    except (TypeError, ValueError):
        return max(0.0, 1000.0 - float(index))
    if 0.0 <= v <= 10.0:
        return v * 1000.0
    return v


def _top_citations_for_llm(
    citations: list[dict[str, Any]],
    user_query: str,
    *,
    limit: int = 5,
    tenant_id: str | None = None,
    fixtures: dict[str, Any] | None = None,
    max_chunks_per_doc: int = 1,
    entity_scope_relaxed: bool = False,
    doc_folder_labels: dict[str, str] | None = None,
    multi_company_scope: bool = False,
    finance_context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """大文件夹检索会返回很多条；按混合分 + 实体/财务关键词重排后取前几条。"""
    if not citations:
        return []
    if len(citations) <= limit and not (user_query or "").strip():
        return citations
    from backend.services.ai_interaction_llm import _load_doc_chunk_text
    from backend.services.knowledge_pipeline import (
        _entity_terms_from_query,
        _expand_retrieval_terms,
        _score_chunk_for_retrieval,
        _tokenize_query,
        fee_breakdown_score_delta,
        is_fee_appendix_chunk,
        query_wants_fee_breakdown,
    )

    terms = _expand_retrieval_terms(_tokenize_query(user_query), user_query, finance_context)
    ents = _entity_terms_from_query(user_query)
    tid = (tenant_id or "").strip() or "tenant1"
    q_join = (user_query or "").replace(" ", "")
    wants_compare = any(x in q_join for x in ("对比", "比较", "两年", "24", "25", "2024", "2025"))
    wants_fee = any(x in q_join for x in ("销售费用", "管理费用", "费用明细", "明细"))
    per_doc_cap = max(1, int(max_chunks_per_doc or 1))
    per_doc: dict[str, list[tuple[float, dict[str, Any]]]] = {}
    for i, c in enumerate(citations):
        if not isinstance(c, dict):
            continue
        base = _citation_base_score(c, i)
        did = str(c.get("doc_id") or "")
        txt = ""
        if did.startswith("ud_"):
            txt = _load_doc_chunk_text(
                tid,
                did,
                str(c.get("chunk_id")) if c.get("chunk_id") else None,
                c.get("chunk_seq_no"),
            ) or ""
        elif fixtures and did:
            for d in fixtures.get("documents") or []:
                if str(d.get("doc_id")) != did:
                    continue
                for s in d.get("sections") or []:
                    for ch in s.get("chunks") or []:
                        if ch.get("chunk_id") == c.get("chunk_id"):
                            txt = str(ch.get("text") or "")
        if txt:
            base += float(
                _score_chunk_for_retrieval(
                    txt,
                    terms,
                    user_query,
                    entity_scope_relaxed=entity_scope_relaxed,
                    finance_context=finance_context,
                )
            )
            if wants_compare or wants_fee:
                money_n = len(re.findall(r"\d{1,3}(?:,\d{3})+\.\d{2}", txt))
                if "目录" in txt and money_n < 2:
                    base -= 450.0
        if did:
            bucket = per_doc.setdefault(did, [])
            bucket.append((base, c))
            bucket.sort(key=lambda x: -x[0])
            per_doc[did] = bucket[:per_doc_cap]
    scored: list[tuple[float, dict[str, Any]]] = []
    for bucket in per_doc.values():
        scored.extend(bucket)
    if not scored:
        scored = [(float(c.get("score") or 0), c) for c in citations if isinstance(c, dict)]
    scored.sort(key=lambda x: -x[0])
    if multi_company_scope and doc_folder_labels and len({doc_folder_labels.get(str(c.get("doc_id") or ""), "") for _, c in scored}) > 1:
        return _diversify_citations_by_folder(scored, doc_folder_labels, limit)
    return [c for _, c in scored[:limit]]


def _diversify_citations_by_folder(
    scored: list[tuple[float, dict[str, Any]]],
    doc_folder_labels: dict[str, str],
    limit: int,
) -> list[dict[str, Any]]:
    """多公司文件夹：每家至少保留一条高分证据，避免 Top-N 被单一主体占满。"""
    by_folder: dict[str, list[tuple[float, dict[str, Any]]]] = {}
    for score, c in scored:
        folder = doc_folder_labels.get(str(c.get("doc_id") or ""), "")
        by_folder.setdefault(folder, []).append((score, c))
    for bucket in by_folder.values():
        bucket.sort(key=lambda x: -x[0])
    picked: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    while len(picked) < limit:
        progressed = False
        for folder in sorted(by_folder.keys(), key=lambda k: -(by_folder[k][0][0] if by_folder[k] else 0)):
            bucket = by_folder[folder]
            while bucket:
                _score, c = bucket.pop(0)
                key = (str(c.get("doc_id") or ""), str(c.get("chunk_id") or ""))
                if key in seen:
                    continue
                seen.add(key)
                picked.append(c)
                progressed = True
                break
            if len(picked) >= limit:
                break
        if not progressed:
            break
    return picked


def build_prefetch_evidence_excerpts(
    citations: list[dict[str, Any]],
    user_query: str,
    *,
    tenant_id: str,
    fixtures: dict[str, Any],
    limit: int = 4,
    excerpt_cap: int = 4000,
    max_chunks_per_doc: int = 1,
    doc_folder_labels: dict[str, str] | None = None,
    finance_context: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    """Top-N chunk 节选，供 Hermes system 注入，减少重复 orientg_kb_ask。"""
    from backend.services.ai_interaction_llm import (
        _evidence_chunk_text_for_llm,
        _load_doc_chunk_text,
        _query_wants_financial_compare,
    )

    labels = doc_folder_labels or {}
    top = _top_citations_for_llm(
        list(citations or []),
        user_query,
        limit=limit,
        tenant_id=tenant_id,
        fixtures=fixtures,
        max_chunks_per_doc=max_chunks_per_doc,
        doc_folder_labels=labels,
        multi_company_scope=len(set(labels.values())) > 1 if labels else False,
        finance_context=finance_context,
    )
    compare_focus = _query_wants_financial_compare(user_query)
    out: list[dict[str, str]] = []
    for c in top:
        if not isinstance(c, dict):
            continue
        did = str(c.get("doc_id") or "")
        txt = ""
        if did.startswith("ud_"):
            txt = (
                _load_doc_chunk_text(
                    tenant_id,
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
        excerpt = _evidence_chunk_text_for_llm(txt, compare_focus=compare_focus)
        src = labels.get(did, "").strip()
        if src:
            excerpt = f"[来源: {src}]\n{excerpt}"
        if len(excerpt) > excerpt_cap:
            excerpt = excerpt[:excerpt_cap] + "\n…（节选截断）"
        out.append(
            {
                "doc_id": did,
                "chunk_id": str(c.get("chunk_id") or ""),
                "excerpt": excerpt,
            }
        )
    return out


def last_user_query(messages: list[dict[str, str]]) -> str:
    for m in reversed(messages or []):
        if m.get("role") == "user":
            return (m.get("content") or "").strip()
    return ""


def should_prefetch_kb(
    kb_scope: dict[str, list[str]] | None,
    *,
    attached_doc_ids: list[str] | None,
) -> bool:
    scope = kb_scope or {}
    if attached_doc_ids:
        return True
    if scope.get("selected_collection_ids") or scope.get("selected_table_ids") or scope.get("selected_folder_ids"):
        return True
    return False


def prefetch_kb_context(
    user_token: str,
    messages: list[dict[str, str]],
    kb_scope: dict[str, list[str]],
    *,
    attached_doc_ids: list[str] | None = None,
    limit_to_attached: bool | None = None,
    agent_mode: str = "standard",
    enabled_skills: list[str] | None = None,
) -> tuple[list[dict[str, str]], dict[str, Any] | None, list[dict[str, Any]]]:
    """
    返回 (带预检索 system 的 messages, ask 结果, tool_calls 片段)。
    无范围或无用户问题时原样返回 messages。
    """
    query = last_user_query(messages)
    if not query:
        return messages, None, []

    fixtures = load_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    resolved = resolve_kb_scope_for_ask(
        tenant_id,
        kb_scope,
        attached_doc_ids=attached_doc_ids,
    )
    cols = list(resolved.get("collection_ids") or [])
    tables = list(resolved.get("table_ids") or [])
    attached = list(resolved.get("attached_doc_ids") or [])
    lim = resolved.get("limit_to_attached") if limit_to_attached is None else limit_to_attached

    from backend.services.kb_retrieve_answer import retrieve_and_answer
    from backend.services.agent_hermes_tier_policy import (
        prefetch_excerpt_limits,
        prefetch_tier_for_agent_mode,
    )

    tier = prefetch_tier_for_agent_mode(agent_mode)
    ask_res, extra_tools = retrieve_and_answer(
        user_token,
        query,
        kb_scope,
        fixtures=fixtures,
        attached_doc_ids=attached_doc_ids,
        limit_to_attached=lim,
        resolved_scope={
            "collection_ids": cols,
            "table_ids": tables,
            "attached_doc_ids": attached,
            "limit_to_attached": bool(lim),
        },
        prefetch_tier=tier,
        enabled_skills=enabled_skills,
    )
    cites = ask_res.get("citations") or []
    evidence_pack = ask_res.get("evidence_pack")
    cite_lines = [
        f"- doc_id={c.get('doc_id')} chunk_id={c.get('chunk_id')}"
        for c in cites[:8]
        if isinstance(c, dict) and c.get("doc_id")
    ]
    task_type_str = str(ask_res.get("task_type") or "")
    from backend.services.agent_hermes_tier_policy import (
        prefetch_excerpt_limits,
        prefetch_tier_for_agent_mode,
    )

    tier = prefetch_tier_for_agent_mode(agent_mode)
    ex_lim, ex_cap, ex_per_doc = prefetch_excerpt_limits(tier, task_type_str)
    pack_labels = {}
    if isinstance(evidence_pack, dict) and isinstance(evidence_pack.get("doc_folder_labels"), dict):
        pack_labels = evidence_pack.get("doc_folder_labels") or {}
    finance_ctx = None
    if isinstance(evidence_pack, dict) and evidence_pack.get("finance_meta"):
        finance_ctx = evidence_pack.get("finance_meta")
    else:
        from backend.services.finance_annual_report_profile import build_finance_retrieval_context

        finance_ctx = build_finance_retrieval_context(enabled_skills, query)
    excerpts = build_prefetch_evidence_excerpts(
        cites,
        query,
        tenant_id=tenant_id,
        fixtures=fixtures,
        limit=ex_lim,
        excerpt_cap=ex_cap,
        max_chunks_per_doc=ex_per_doc,
        doc_folder_labels=pack_labels,
        finance_context=finance_ctx if isinstance(finance_ctx, dict) else None,
    )
    from backend.services.evidence_pack import pack_summary_for_sse

    pack_compact = None
    if isinstance(evidence_pack, dict):
        pack_compact = {
            **(pack_summary_for_sse(evidence_pack) or {}),
            "facets": list(evidence_pack.get("facets") or [])[:8],
        }
    compact = {
        "ok": ask_res.get("ok"),
        "reply": ask_res.get("reply"),
        "reason": ask_res.get("reason"),
        "citations": cites[:12],
        "evidence_excerpts": excerpts,
        "evidence_pack": pack_compact,
        "task_type": ask_res.get("task_type"),
        "partial_denied": bool(ask_res.get("partial_denied")),
    }
    from backend.services.agent_hermes_tier_policy import (
        discourage_repeat_kb_ask,
        prefetch_system_lead,
    )

    via_hermes = bool(settings.hermes_configured and settings.hermes_agent_kb_synthesize)
    pack_dict = evidence_pack if isinstance(evidence_pack, dict) else None
    lead = prefetch_system_lead(
        via_hermes=via_hermes,
        evidence_pack=pack_dict,
        tier=tier,
    )
    if via_hermes and ask_res.get("ok") and (ask_res.get("citations") or []) and discourage_repeat_kb_ask(tier):
        lead += (
            "【检索策略】除非证据明显不足或需切换口径（如合并↔母公司），请勿重复调用 orientg_kb_ask；"
            "需要补充检索时请换用更具体 query（如「合并利润表 营业收入 2025」）。\n"
        )
    prefetch_msg = {
        "role": "system",
        "content": (
            lead
            + f"摘要：{compact.get('reply') or ''}\n"
            + ("引用：\n" + "\n".join(cite_lines) + "\n" if cite_lines else "")
            + "详情 JSON：\n"
            + json.dumps(compact, ensure_ascii=False)
        ),
    }
    out_messages = [prefetch_msg, *messages]
    tc = list(extra_tools) if extra_tools else [
        {
            "name": "orientg_kb_ask",
            "status": "ok" if ask_res.get("ok") else "denied",
            "prefetch": True,
            "result": ask_res,
        }
    ]
    if ask_res.get("ok") and evidence_pack is not None:
        ask_res = {**ask_res, "evidence_pack": evidence_pack}
    return out_messages, ask_res, tc


def synthesize_kb_reply(
    *,
    tenant_id: str,
    user_query: str,
    prefetch_result: dict[str, Any],
    fixtures: dict[str, Any],
    enabled_skills: list[str] | None = None,
    model: str | None = None,
    skill_addon_extra: str | None = None,
    run_id: str | None = None,
    cite_limit: int | None = None,
    extra_evidence_blocks: list[str] | None = None,
) -> dict[str, Any]:
    """
    与 /api/ai-interaction/chat 一致：检索摘要仅供观测，面向用户的答复由 LLM 基于 citations 生成。
    """
    pack = prefetch_result.get("evidence_pack") or {}
    task_type = str(pack.get("task_type") or prefetch_result.get("task_type") or "")
    relax_entity = bool(pack.get("entity_scope_relaxed"))
    doc_labels = pack.get("doc_folder_labels") if isinstance(pack.get("doc_folder_labels"), dict) else {}
    multi_co = bool(pack.get("multi_company_scope"))
    finance_ctx = pack.get("finance_meta") if isinstance(pack.get("finance_meta"), dict) else None
    if not finance_ctx:
        from backend.services.finance_annual_report_profile import build_finance_retrieval_context

        finance_ctx = build_finance_retrieval_context(enabled_skills, user_query)
    max_per_doc = 2 if task_type == "breakdown" else 1
    default_limit = 12 if multi_co else (10 if task_type in ("breakdown", "compare") else 5)
    cite_lim = int(cite_limit) if cite_limit is not None else default_limit
    citations = _top_citations_for_llm(
        list(prefetch_result.get("citations") or []),
        user_query,
        limit=cite_lim,
        tenant_id=tenant_id,
        fixtures=fixtures,
        max_chunks_per_doc=max_per_doc,
        entity_scope_relaxed=relax_entity,
        doc_folder_labels=doc_labels,
        multi_company_scope=multi_co,
        finance_context=finance_ctx if isinstance(finance_ctx, dict) else None,
    )
    if prefetch_result.get("denied"):
        return {
            "ok": False,
            "reply": prefetch_result.get("deny_reason") or prefetch_result.get("reason") or "denied",
            "citations": citations,
            "synthesis": "denied",
        }

    from backend.services.agent_run_registry import is_cancelled

    if is_cancelled(run_id):
        return {
            "ok": False,
            "reply": "已停止",
            "citations": citations,
            "synthesis": "cancelled",
        }

    if not settings.chat_llm_available:
        reply = (prefetch_result.get("reply") or "").strip() or "（检索无摘要）"
        if citations:
            reply += f"\n\n（共 {len(citations)} 条引用，未配置对话 LLM）"
        return {
            "ok": True,
            "reply": reply,
            "citations": citations,
            "synthesis": "prefetch_only",
        }

    from backend.services.agent_skills_loader import build_system_addon_for_enabled_skills
    from backend.services.ai_interaction_llm import generate_answer_with_evidence

    use_model = (model or "").strip() or (
        (settings.llm_model or "").strip() if settings.llm_chat_configured else (settings.ollama_model or "").strip()
    ) or settings.ollama_model
    skill_addon = build_system_addon_for_enabled_skills(enabled_skills or [])
    extra = (skill_addon_extra or "").strip()
    if extra:
        skill_addon = "\n\n".join(x for x in [(skill_addon or "").strip(), extra] if x)
    try:
        llm_reply = generate_answer_with_evidence(
            tenant_id=tenant_id,
            model=use_model,
            user_query=user_query,
            citations=citations,
            fixtures=fixtures,
            skill_addon=skill_addon or None,
            extra_evidence_blocks=extra_evidence_blocks,
        )
        return {
            "ok": True,
            "reply": llm_reply,
            "citations": citations,
            "synthesis": "local_llm",
            "llm_model": use_model,
        }
    except Exception as e:
        import re

        n = len(citations)
        doc_ids = sorted({str(c.get("doc_id")) for c in citations if isinstance(c, dict) and c.get("doc_id")})[:8]
        from backend.services.evidence_reply_align import build_evidence_synth_fallback_reply

        fallback = build_evidence_synth_fallback_reply(
            user_query,
            citations=citations,
            evidence_pack=pack if isinstance(pack, dict) else None,
        )
        if fallback and (
            re.search(r"\d{1,3}(?:,\d{3})+\.\d{2}", fallback) or "缺少证据" in fallback
        ):
            reply = fallback
            synthesis = "prefetch_fallback_evidence"
        else:
            reply = (
                f"已从知识库检索到 {n} 条相关证据，但基于证据生成回答时超时或失败（{e}）。"
                "请缩小知识库范围后重试，或到左侧「对话」页使用相同范围提问。"
            )
            synthesis = "prefetch_fallback"
            if doc_ids:
                reply += "\n\n相关 doc_id：" + "、".join(doc_ids)
        return {
            "ok": True,
            "reply": reply,
            "citations": citations,
            "synthesis": synthesis,
            "llm_model": use_model,
        }
