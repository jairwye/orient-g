"""Hermes 未调用 MCP 时，Orient-G 网关自动补检索并修订答案。"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

from backend.services.agent_kb_router import AgentRoute
from backend.services.evidence_pack import build_evidence_pack, merge_citations
from backend.services.evidence_reply_align import (
    pack_amounts_for_alignment,
    pack_has_tabular_breakdown,
    reply_amount_coverage,
    reply_falsely_denies_kb_breakdown,
    reply_has_contradictory_change_reason,
    reply_has_derived_breakdown_amounts,
    reply_has_gap_placeholder,
)
from backend.services.kb_retrieval_plan import TaskType, infer_task_type
from backend.services.knowledge_pipeline import ask_knowledge


def _money_amount_count(text: str) -> int:
    return len(re.findall(r"\d{1,3}(?:,\d{3})+\.\d{2}", text or ""))


def _is_missing_evidence_reply(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return True
    if "缺少证据" in t or "不确定/缺少证据" in t:
        return _money_amount_count(t) < 2
    return False


def _citation_keys(citations: list[dict[str, Any]]) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for c in citations or []:
        if not isinstance(c, dict):
            continue
        out.add((str(c.get("doc_id") or ""), str(c.get("chunk_id") or c.get("chunk_seq_no") or "")))
    return out


def count_new_citation_keys(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> int:
    return len(_citation_keys(after) - _citation_keys(before))


def hermes_reply_needs_breakdown_revise(
    hermes_reply: str,
    *,
    prefetch_result: dict[str, Any] | None,
    user_query: str,
) -> bool:
    """Tier 2：Hermes 未 kb_ask 且终稿缺分项/含估算时，须网关补检索+修订。"""
    from backend.services.hermes_stream_sanitize import reply_has_unsupported_estimates

    pack = (prefetch_result or {}).get("evidence_pack") or {}
    tt = str(pack.get("task_type") or infer_task_type(user_query).value)
    if tt not in (TaskType.breakdown.value, TaskType.compare.value):
        return False
    h = hermes_reply or ""
    if reply_has_unsupported_estimates(h):
        return True
    if reply_has_derived_breakdown_amounts(h):
        return True
    if reply_has_contradictory_change_reason(h):
        return True
    if reply_falsely_denies_kb_breakdown(h, user_query=user_query):
        return True
    if reply_has_gap_placeholder(h):
        return True
    if not pack_has_tabular_breakdown(pack):
        return False
    anchors = pack_amounts_for_alignment(pack)
    if anchors and reply_amount_coverage(h, anchors) < 0.45:
        return True
    from backend.services.kb_retrieval_plan import query_wants_analyst_report

    if query_wants_analyst_report(user_query) and len(h.strip()) < 2200:
        return True
    return False


def pack_facet_evidence_blocks(pack: dict[str, Any] | None, *, limit: int = 8) -> list[str]:
    facets = (pack or {}).get("facets") or []
    out: list[str] = []
    for f in facets[:limit]:
        if not isinstance(f, dict):
            continue
        excerpt = str(f.get("excerpt") or "").strip()
        if not excerpt:
            continue
        label = str(f.get("label") or "facet")
        out.append(f"[evidence_pack {label}] {excerpt[:8000]}")
    return out


def choose_supplemental_reply(
    *,
    hermes_reply: str,
    synth_reply: str,
    prefetch_result: dict[str, Any] | None = None,
) -> tuple[str, bool, str]:
    """
    返回 (最终正文, 是否采用 synthesize, 说明)。
    采用 pack 金额覆盖率等通用规则，不绑定具体 doc/公司锚点。
    """
    from backend.services.hermes_stream_sanitize import (
        enforce_breakdown_compare_reply,
        reply_has_unsupported_estimates,
    )

    pack = (prefetch_result or {}).get("evidence_pack") or {}
    anchors = pack_amounts_for_alignment(pack if isinstance(pack, dict) else None)

    h_raw = hermes_reply or ""
    h = enforce_breakdown_compare_reply(h_raw, user_query="")
    s = (synth_reply or "").strip()
    if not s:
        return h, False, "synth_empty"
    if not h:
        return s, True, "hermes_empty"

    h_cov = reply_amount_coverage(h_raw, anchors) if anchors else reply_amount_coverage(h, anchors)
    s_cov = reply_amount_coverage(s, anchors)

    h_est = reply_has_unsupported_estimates(h_raw)
    s_est = reply_has_unsupported_estimates(s)
    h_derived = reply_has_derived_breakdown_amounts(h_raw)
    s_derived = reply_has_derived_breakdown_amounts(s)
    h_money = _money_amount_count(h)
    s_money = _money_amount_count(s)

    if s_derived and not h_derived and s_money >= 1:
        return h if h_money >= 1 else s, False, "reject_synth_derived_amounts"
    if h_derived and not s_derived and s_money >= 2 and not _is_missing_evidence_reply(s):
        return s, True, "synth_no_derived_amounts"
    if reply_has_contradictory_change_reason(s) and not reply_has_contradictory_change_reason(h_raw):
        return h, False, "reject_synth_contradictory_reason"

    if anchors and s_cov >= h_cov + 0.2 and s_money >= 2 and not _is_missing_evidence_reply(s):
        return s, True, "synth_better_pack_coverage"
    if reply_has_gap_placeholder(h) and not reply_has_gap_placeholder(s) and s_money >= 2:
        return s, True, "synth_fills_gap_placeholder"
    if h_est and not s_est and s_money >= 2 and not _is_missing_evidence_reply(s):
        return s, True, "synth_no_estimates"
    if h_est and not s_est and _is_missing_evidence_reply(s) and h_money >= 2:
        return h, False, "hermes_stripped_estimates"
    if _is_missing_evidence_reply(s) and h_money >= 2:
        return h, False, "keep_hermes_has_amounts"
    if _is_missing_evidence_reply(s) and not _is_missing_evidence_reply(h):
        return h, False, "keep_hermes_richer"
    if s_money > h_money:
        return s, True, "synth_more_amounts"
    if s_money == h_money and len(s) > len(h) and not _is_missing_evidence_reply(s):
        return s, True, "synth_same_amounts_more_detail"
    if h_money > s_money and h_cov >= s_cov:
        return h, False, "keep_hermes_more_amounts"
    return s, True, "default_synth"


def evidence_constraint_addon(*, tier: str) -> str:
    """breakdown/compare 分项禁止幻觉（Tier 0/1/2 补检索修订均适用）。"""
    t = (tier or "local").strip().lower()
    if t not in ("local", "lite", "full"):
        return ""
    return (
        "【证据约束】禁止「估算」「约 xxx 万」「推断」「合理推测」「计算得出」「减去变动额反推」"
        "作为分项金额或未引用的原因；"
        "每个数字须能在引用片段原文中找到。"
        "若证据含总额与分项金额，须写入对比表；pack 中已有分项时不得写「证据无分项」。"
        "定性变动原因仅可来自证据原文（如「主要系…」「是由于…」）；无原因文字时写"
        "「证据未提供变动原因说明，仅列示金额与分项对比」。"
        "不得在同一报告中既写「无变动原因」又引用原因原文。"
    )


def supplemental_answer_addon(*, user_query: str, tier: str) -> str:
    from backend.services.agent_kb_fast_path import comparison_answer_addon

    t = (tier or "lite").strip().lower()
    if t == "hermes_lite":
        t = "lite"
    parts = [
        x
        for x in [
            evidence_constraint_addon(tier=t if t in ("local", "lite", "full") else "lite"),
            comparison_answer_addon(
                user_query,
                tier=t if t in ("local", "lite", "full") else "lite",
            ),
        ]
        if x
    ]
    return "\n\n".join(parts)


def hermes_orientg_kb_ask_count(*, hermes_payload: dict[str, Any] | None) -> int:
    payload = hermes_payload or {}
    stats = payload.get("hermes_stream_stats") or {}
    n = int(stats.get("orientg_kb_ask_calls") or 0)
    if n > 0:
        return n
    for tc in payload.get("tool_calls") or []:
        if not isinstance(tc, dict) or tc.get("prefetch"):
            continue
        name = str(tc.get("name") or "")
        if "orientg_kb" in name:
            n += 1
    return n


def prefetch_defers_hermes_draft_to_process(
    *,
    agent_route: AgentRoute | str,
    prefetch_result: dict[str, Any] | None,
) -> bool:
    """
    breakdown/compare 且预检索成功：Hermes 流式正文先进执行过程，终稿由 done/补检索决定。
    避免「先显示 Hermes 初稿、补检索后又替换」的主气泡闪烁。
    """
    route = agent_route.value if isinstance(agent_route, AgentRoute) else str(agent_route)
    if route not in (AgentRoute.hermes_lite.value, AgentRoute.hermes_full.value):
        return False
    pack = (prefetch_result or {}).get("evidence_pack") or {}
    # 仅 breakdown 过程稿进「执行过程」；compare（如两年末余额对比）须 Hermes 正文进主气泡，避免 hermes_empty 回退
    if str(pack.get("task_type") or "") != TaskType.breakdown.value:
        return False
    return bool((prefetch_result or {}).get("ok"))


def needs_hermes_supplemental(
    *,
    agent_route: AgentRoute | str,
    prefetch_result: dict[str, Any] | None,
    hermes_kb_ask_count: int,
    hermes_reply: str = "",
    user_query: str = "",
) -> bool:
    route = agent_route.value if isinstance(agent_route, AgentRoute) else str(agent_route)
    if route not in (AgentRoute.hermes_lite.value, AgentRoute.hermes_full.value):
        return False
    if hermes_kb_ask_count > 0:
        return False
    pack = (prefetch_result or {}).get("evidence_pack") or {}
    if str(pack.get("task_type") or "") not in (TaskType.breakdown.value, TaskType.compare.value):
        return False
    if not (prefetch_result or {}).get("ok"):
        return False
    # Tier 2：仅在 Hermes 偷懒（估算/缺分项）且预检索 pack 有分项证据时修订，非整篇无脑覆盖
    if route == AgentRoute.hermes_full.value:
        return hermes_reply_needs_breakdown_revise(
            hermes_reply,
            prefetch_result=prefetch_result,
            user_query=user_query,
        )
    return True


def plan_supplemental_queries(
    user_query: str,
    *,
    evidence_pack: dict[str, Any] | None,
    max_queries: int = 5,
) -> list[str]:
    """基于 task_type + 用户问句生成补检索 query（与预检索 plan 同源，跳过已用 query）。"""
    from backend.services.kb_retrieval_plan import TaskType, detect_entity, infer_task_type, plan_retrieval_queries

    q = (user_query or "").strip()
    if not q:
        return []
    pack = evidence_pack or {}
    tt_raw = str(pack.get("task_type") or infer_task_type(q).value)
    try:
        tt = TaskType(tt_raw)
    except ValueError:
        tt = infer_task_type(q)
    used = {str(x).strip() for x in (pack.get("retrieval_queries") or []) if str(x).strip()}
    ent = detect_entity(q)
    candidates = plan_retrieval_queries(
        q,
        tt,
        entity=ent,
        max_queries=max(max_queries + len(used), 8),
        prefetch_tier="lite",
    )
    out: list[str] = []
    for cand in candidates:
        c = (cand or "").strip()
        if not c or c in used or c in out:
            continue
        out.append(c)
        if len(out) >= max_queries:
            break
    return out


def run_supplemental_kb_asks(
    *,
    user_token: str,
    user_query: str,
    prefetch_result: dict[str, Any],
    kb_scope: dict[str, list[str]],
    attached_doc_ids: list[str] | None,
    fixtures: dict[str, Any],
    max_queries: int = 5,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """执行补检索；返回 (merged_prefetch, tool_calls)。无新 query 时 (None, [])。"""
    pack = prefetch_result.get("evidence_pack") or {}
    queries = plan_supplemental_queries(user_query, evidence_pack=pack, max_queries=max_queries)
    if not queries:
        return None, []

    from backend.services.kb_scope_resolve import resolve_kb_scope_for_ask

    tenant_id = fixtures.get("tenant_id") or "tenant1"
    resolved = resolve_kb_scope_for_ask(
        tenant_id,
        kb_scope,
        attached_doc_ids=attached_doc_ids,
    )
    cols = list(resolved.get("collection_ids") or [])
    tables = list(resolved.get("table_ids") or [])
    attached = list(resolved.get("attached_doc_ids") or [])
    lim = resolved.get("limit_to_attached")

    tool_calls: list[dict[str, Any]] = []
    cite_lists: list[list[dict[str, Any]]] = [list(prefetch_result.get("citations") or [])]
    reply_parts: list[str] = []
    if prefetch_result.get("reply"):
        reply_parts.append(str(prefetch_result.get("reply")))

    for sub_q in queries:
        res = ask_knowledge(
            user_token,
            sub_q,
            selected_collection_ids=cols or None,
            selected_table_ids=tables or None,
            fixtures=fixtures,
            attached_doc_ids=attached or None,
            limit_to_attached=bool(lim),
        )
        status = "ok" if not res.get("denied") else "denied"
        cites = list(res.get("citations") or [])
        if cites:
            cite_lists.append(cites)
        if res.get("reply"):
            reply_parts.append(str(res.get("reply")))
        tool_calls.append(
            {
                "name": "orientg_kb_ask",
                "status": status,
                "supplemental": True,
                "query": sub_q,
                "result": res,
            }
        )

    merged_cites = merge_citations(cite_lists)
    old_queries = list(pack.get("retrieval_queries") or [])
    all_queries = old_queries + [q for q in queries if q not in old_queries]
    task_type = str(pack.get("task_type") or infer_task_type(user_query).value)
    new_pack = build_evidence_pack(
        user_query=user_query,
        task_type=task_type,
        retrieval_queries=all_queries,
        citations=merged_cites,
        reply_parts=reply_parts,
        tenant_id=tenant_id,
        fixtures=fixtures,
    )
    merged = {
        **prefetch_result,
        "ok": True,
        "citations": merged_cites,
        "reply": new_pack.get("reply") or prefetch_result.get("reply") or "",
        "evidence_pack": new_pack,
        "kb_supplemental": True,
    }
    return merged, tool_calls


def iter_supplemental_revision_events(
    *,
    user_token: str,
    tenant_id: str,
    user_query: str,
    prefetch_result: dict[str, Any],
    prefetch_tool_calls: list[dict[str, Any]],
    kb_scope: dict[str, list[str]],
    attached_doc_ids: list[str] | None,
    fixtures: dict[str, Any],
    agent_route: AgentRoute,
    enabled_skills: list[str] | None,
    model: str | None,
    hermes_reply: str,
    run_id: str | None = None,
) -> Iterator[dict[str, Any]]:
    """产出补检索 + 本地重综合 SSE 事件（在 Hermes done 之后）。"""
    from backend.services.agent_kb_prefetch import synthesize_kb_reply
    from backend.services.agent_hermes_tier_policy import prefetch_tier_from_route
    from backend.services.agent_run_registry import is_cancelled

    if is_cancelled(run_id):
        return

    tier = prefetch_tier_from_route(agent_route.value)
    yield {
        "type": "status",
        "message": "Hermes 未调用 MCP 补检索；Orient-G 自动执行定向 orientg_kb_ask…",
        "step": "supplemental_kb",
    }
    merged, sup_tools = run_supplemental_kb_asks(
        user_token=user_token,
        user_query=user_query,
        prefetch_result=prefetch_result,
        kb_scope=kb_scope,
        attached_doc_ids=attached_doc_ids,
        fixtures=fixtures,
    )
    for tc in sup_tools:
        q = str(tc.get("query") or "")[:60]
        yield {
            "type": "tool_call",
            "name": "orientg_kb_ask",
            "status": tc.get("status") or "ok",
            "message": f"补检索：{q}" if q else "补检索：orientg_kb_ask",
        }
    use_prefetch = merged if merged else prefetch_result
    if not sup_tools:
        yield {
            "type": "status",
            "message": "无额外补检索 query；基于证据约束重新综合…",
            "step": "supplemental_synth",
        }
    else:
        yield {
            "type": "status",
            "message": f"补检索完成（{len(sup_tools)} 次）；Orient-G 重新综合答案…",
            "step": "supplemental_synth",
        }
    if is_cancelled(run_id):
        yield {"type": "error", "message": "已停止", "code": "cancelled"}
        return
    before_cites = list(prefetch_result.get("citations") or [])
    extra_blocks = pack_facet_evidence_blocks(use_prefetch.get("evidence_pack"))
    synth = synthesize_kb_reply(
        tenant_id=tenant_id,
        user_query=user_query,
        prefetch_result=use_prefetch,
        fixtures=fixtures,
        enabled_skills=enabled_skills,
        model=model,
        skill_addon_extra=supplemental_answer_addon(user_query=user_query, tier=tier) or None,
        cite_limit=12,
        extra_evidence_blocks=extra_blocks or None,
        run_id=run_id,
    )
    synth_reply = (synth.get("reply") or "").strip()
    final_reply, adopted, reason = choose_supplemental_reply(
        hermes_reply=hermes_reply,
        synth_reply=synth_reply,
        prefetch_result=use_prefetch,
    )
    from backend.services.hermes_stream_sanitize import finalize_agent_reply

    final_reply = finalize_agent_reply(
        final_reply,
        user_query=user_query,
        tier2_native=(agent_route == AgentRoute.hermes_full),
    )
    new_keys = count_new_citation_keys(before_cites, list(use_prefetch.get("citations") or []))
    hermes_stripped = (hermes_reply or "").strip() != final_reply.strip()
    if not adopted:
        msg = (
            "补检索已完成；已整理正文格式并应用证据约束"
            if hermes_stripped
            else "补检索已完成，但本地重综合未优于 Hermes 原文（已保留 Hermes 答案，避免「缺少证据」覆盖已有金额）"
        )
        yield {
            "type": "status",
            "message": msg,
            "step": "supplemental_keep_hermes",
        }
    elif new_keys > 0:
        yield {
            "type": "status",
            "message": f"已采用补检索修订（新增证据 {new_keys} 条，{reason}）",
            "step": "supplemental_adopted",
        }
    if final_reply.strip() and final_reply.strip() != (hermes_reply or "").strip():
        yield {"type": "replace_reply", "content": final_reply}
    yield {
        "type": "supplemental_meta",
        "reply": final_reply,
        "citations": synth.get("citations") or use_prefetch.get("citations") or [],
        "tool_calls": sup_tools,
        "prefetch_result": use_prefetch,
        "synthesis": synth.get("synthesis") if adopted else "hermes_kept",
        "llm_model": synth.get("llm_model"),
        "supplemental_adopted": adopted,
        "supplemental_reason": reason,
    }


def apply_supplemental_to_done(
    done_evt: dict[str, Any],
    *,
    supplemental_meta: dict[str, Any],
    prefetch_tool_calls: list[dict[str, Any]],
) -> dict[str, Any]:
    sup_tools = list(supplemental_meta.get("tool_calls") or [])
    prefetch = supplemental_meta.get("prefetch_result") or {}
    pack = prefetch.get("evidence_pack")
    from backend.services.evidence_pack import pack_summary_for_sse

    stats = dict(done_evt.get("hermes_stream_stats") or {})
    stats["orientg_kb_supplemental_calls"] = len(sup_tools)
    base_tools = list(done_evt.get("tool_calls") or [])
    base_tools.extend(sup_tools)
    return {
        **done_evt,
        "reply": supplemental_meta.get("reply") or done_evt.get("reply"),
        "citations": supplemental_meta.get("citations") or done_evt.get("citations"),
        "tool_calls": base_tools,
        "evidence_pack": pack_summary_for_sse(pack if isinstance(pack, dict) else None),
        "kb_supplemental": True,
        "synthesis": supplemental_meta.get("synthesis") or done_evt.get("synthesis"),
        "supplemental_adopted": supplemental_meta.get("supplemental_adopted"),
        "supplemental_reason": supplemental_meta.get("supplemental_reason"),
        "llm_model": supplemental_meta.get("llm_model") or done_evt.get("llm_model"),
        "hermes_stream_stats": stats,
    }
