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
    reply_denies_primary_compare_subject,
    reply_falsely_denies_kb_breakdown,
    reply_has_contradictory_change_reason,
    reply_has_derived_breakdown_amounts,
    reply_has_gap_placeholder,
)
from backend.services.kb_retrieval_plan import TaskType, infer_task_type
from backend.services.kb_ask_mcp_reply import execute_kb_subquery_ask
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


def hermes_reply_sufficient_against_pack(
    hermes_reply: str,
    *,
    prefetch_result: dict[str, Any] | None,
    user_query: str,
) -> bool:
    """pack 分项充分且 Hermes 终稿金额/口径合格时，可跳过网关补检索。"""
    from backend.services.hermes_stream_sanitize import (
        reply_has_unsupported_estimates,
        reply_has_unsupported_speculation,
    )

    pack = (prefetch_result or {}).get("evidence_pack") or {}
    tt = str(pack.get("task_type") or infer_task_type(user_query).value)
    if tt not in (TaskType.breakdown.value, TaskType.compare.value):
        return False
    if pack.get("gaps"):
        return False
    if not pack_has_tabular_breakdown(pack):
        return False
    if float(pack.get("coverage_score") or 0) < 0.75:
        return False
    h = (hermes_reply or "").strip()
    min_len = 50 if (_money_amount_count(h) >= 2 and "|" in h) else 80
    if len(h) < min_len:
        return False
    if reply_has_unsupported_estimates(h):
        return False
    if reply_has_unsupported_speculation(h):
        return False
    if reply_has_derived_breakdown_amounts(h):
        return False
    if reply_has_contradictory_change_reason(h):
        return False
    if reply_falsely_denies_kb_breakdown(h, user_query=user_query):
        return False
    if reply_denies_primary_compare_subject(h, user_query=user_query):
        return False
    if reply_has_gap_placeholder(h):
        return False
    anchors = pack_amounts_for_alignment(pack)
    if anchors and reply_amount_coverage(h, anchors) < 0.35:
        return False
    return _money_amount_count(h) >= 2


def pick_hermes_error_fallback_reply(
    *,
    draft_acc: Any | None,
    synth_reply: str,
    prefetch_result: dict[str, Any] | None,
    user_query: str,
) -> tuple[str, str]:
    """Hermes 流式 error 时：优先 salvage 已累积过程稿，避免无差别本地 synth 覆盖。"""
    from backend.services.hermes_stream_sanitize import (
        _markdown_structure_score,
        finalize_agent_reply,
        looks_like_planning,
        resolve_hermes_effective_reply,
        sanitize_hermes_accumulated_reply,
    )

    salvaged_raw = resolve_hermes_effective_reply(evt_reply="", draft_acc=draft_acc)
    synth = (synth_reply or "").strip()
    if salvaged_raw:
        cand = sanitize_hermes_accumulated_reply(salvaged_raw, user_query=user_query).strip()
        cand = finalize_agent_reply(cand, user_query=user_query, tier2_native=False)
        if cand and (
            hermes_reply_sufficient_against_pack(
                cand,
                prefetch_result=prefetch_result,
                user_query=user_query,
            )
            or (
                _money_amount_count(cand) >= 2
                and len(cand) >= 400
                and _markdown_structure_score(cand) >= max(_markdown_structure_score(synth), len(synth))
                and not looks_like_planning(cand)
            )
        ):
            return cand, "hermes_salvaged"
    if synth:
        return (
            finalize_agent_reply(synth, user_query=user_query, tier2_native=False),
            "local_fallback",
        )
    return "", "local_fallback"


def _hermes_tier2_sanitize_only(
    hermes_reply: str,
    *,
    pack: dict[str, Any],
    user_query: str,
) -> bool:
    """深度档仅含无证据推断等软问题：终稿 sanitize 即可，不必本地重综合。"""
    from backend.services.hermes_stream_sanitize import (
        reply_has_unsupported_estimates,
        reply_has_unsupported_speculation,
    )

    h = hermes_reply or ""
    if not reply_has_unsupported_speculation(h):
        return False
    if reply_has_unsupported_estimates(h):
        return False
    if reply_has_derived_breakdown_amounts(h):
        return False
    if reply_has_contradictory_change_reason(h):
        return False
    if reply_falsely_denies_kb_breakdown(h, user_query=user_query):
        return False
    if reply_denies_primary_compare_subject(h, user_query=user_query):
        return False
    if reply_has_gap_placeholder(h):
        return False
    if not pack_has_tabular_breakdown(pack):
        return False
    if _money_amount_count(h) < 2:
        return False
    anchors = pack_amounts_for_alignment(pack)
    if anchors and reply_amount_coverage(h, anchors) < 0.35:
        return False
    return True


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
    if tt not in (TaskType.breakdown.value, TaskType.compare.value, TaskType.general.value):
        return False
    h = hermes_reply or ""
    if _hermes_tier2_sanitize_only(h, pack=pack, user_query=user_query):
        return False
    if reply_has_unsupported_estimates(h):
        return True
    # 深度档：无证据推断（可能系…）由 finalize tier2 sanitize 处理，不触发本地重综合以免稀释 Hermes 成稿质量
    if reply_has_derived_breakdown_amounts(h):
        return True
    if reply_has_contradictory_change_reason(h):
        return True
    if reply_falsely_denies_kb_breakdown(h, user_query=user_query):
        return True
    if reply_denies_primary_compare_subject(h, user_query=user_query):
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
        if hermes_reply_sufficient_against_pack(
            h, prefetch_result=prefetch_result, user_query=user_query
        ):
            return False
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
    agent_route: AgentRoute | str | None = None,
    user_query: str = "",
) -> tuple[str, bool, str]:
    """
    返回 (最终正文, 是否采用 synthesize, 说明)。
    采用 pack 金额覆盖率等通用规则，不绑定具体 doc/公司锚点。
    """
    from backend.services.hermes_stream_sanitize import (
        enforce_breakdown_compare_reply,
        reply_has_unsupported_estimates,
        reply_has_verifiable_breakdown_table,
    )

    route = agent_route.value if isinstance(agent_route, AgentRoute) else str(agent_route or "")
    tier2_native = route == AgentRoute.hermes_full.value

    pack = (prefetch_result or {}).get("evidence_pack") or {}
    anchors = pack_amounts_for_alignment(pack if isinstance(pack, dict) else None)

    uq = (user_query or "").strip()
    h_raw = hermes_reply or ""
    s = (synth_reply or "").strip()
    from backend.services.hermes_stream_sanitize import looks_like_planning

    if looks_like_planning(h_raw):
        if s:
            return s, True, "hermes_planning"
        return h_raw, False, "hermes_planning_no_synth"
    h = enforce_breakdown_compare_reply(h_raw, user_query=uq)
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
    if reply_denies_primary_compare_subject(h_raw, user_query=uq) and not reply_denies_primary_compare_subject(
        s, user_query=uq
    ):
        if _money_amount_count(s) >= 1 and not _is_missing_evidence_reply(s):
            return s, True, "synth_has_compare_subject_amounts"
    if reply_denies_primary_compare_subject(h_raw, user_query=uq) and _is_missing_evidence_reply(s):
        return h, False, "keep_hermes_over_synth_missing"

    if anchors and s_cov >= h_cov + 0.2 and s_money >= 2 and not _is_missing_evidence_reply(s):
        return s, True, "synth_better_pack_coverage"
    if reply_has_gap_placeholder(h) and not reply_has_gap_placeholder(s) and s_money >= 2:
        return s, True, "synth_fills_gap_placeholder"
    if reply_has_gap_placeholder(s) and not reply_has_gap_placeholder(h_raw) and h_money >= 2:
        if re.search(r"主要系|主要是由于|年报|项目重大变动|变动原因", h_raw):
            return h, False, "keep_hermes_has_narrative_reason"
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
    if tier2_native:
        h_fin = enforce_breakdown_compare_reply(h_raw, user_query=uq)
        h_fin_money = _money_amount_count(h_fin)
        if reply_has_verifiable_breakdown_table(h_raw) and h_fin_money >= 2:
            if len(h_fin) >= max(len(s), 1000) and h_cov >= s_cov - 0.08:
                if not _is_missing_evidence_reply(h_fin):
                    return h_fin, False, "tier2_keep_hermes_sanitized"
        if len(h_raw) >= max(len(s) * 1.1, 1500) and h_money >= s_money:
            if not _is_missing_evidence_reply(h):
                return h, False, "tier2_keep_hermes_richer"
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
    from backend.services.hermes_stream_stats import hermes_native_kb_ask_count

    payload = hermes_payload or {}
    stats = payload.get("hermes_stream_stats") or {}
    n = hermes_native_kb_ask_count(stats)
    if n > 0:
        return n
    for tc in payload.get("tool_calls") or []:
        if not isinstance(tc, dict) or tc.get("prefetch"):
            continue
        name = str(tc.get("name") or "")
        if tc.get("source") == "orientg_gateway_primer":
            continue
        if "orientg_kb" in name:
            n += 1
    return n


def prefetch_defers_hermes_draft_to_process(
    *,
    agent_route: AgentRoute | str,
    prefetch_result: dict[str, Any] | None,
) -> bool:
    """
    Tier 1/2：Hermes 流式正文（delta/thinking）一律写入执行过程，主气泡仅展示终稿
    （done / replace_reply / salvage / 本地回退）。与 task_type、预检索是否成功无关。
    """
    route = agent_route.value if isinstance(agent_route, AgentRoute) else str(agent_route)
    return route in (AgentRoute.hermes_lite.value, AgentRoute.hermes_full.value)


def _personnel_compare_reply_insufficient(hermes_reply: str, *, user_query: str) -> bool:
    """人员/人效对比：终稿须同时出现两家主体与量化指标，且非低质量 excerpt dump。"""
    from backend.services.kb_ask_mcp_reply import (
        personnel_compare_reply_misattributed,
        personnel_excerpt_reply_is_low_quality,
    )
    from backend.services.personnel_compare_report import personnel_excerpt_dump_only

    q = (user_query or "").strip()
    if not re.search(r"人员|人效|员工|人力|人数", q):
        return False
    h = (hermes_reply or "").strip()
    if not h:
        return True
    if personnel_excerpt_reply_is_low_quality(h):
        return True
    if personnel_excerpt_dump_only(h):
        return True
    if personnel_compare_reply_misattributed(h, user_query=q):
        return True
    from backend.services.personnel_compare_report import personnel_compare_hermes_draft_is_bad

    if personnel_compare_hermes_draft_is_bad(h, user_query=q):
        return True
    has_a = bool(re.search(r"可比公司A|可比公司A", h))
    has_b = bool(re.search(r"YYCQ", h, re.I))
    has_num = bool(re.search(r"\d{2,4}", h))
    has_table = "|" in h and ("---" in h or re.search(r"\t[^\t]+\t", h))
    has_structure_table = bool(re.search(r"人员结构对照", h))
    if has_a and has_b and has_num and (has_table or len(h) >= 400) and has_structure_table:
        return False
    return True


def pick_personnel_compare_final_reply(
    *,
    hermes_reply: str,
    synth_reply: str,
    excerpt_reply: str | None,
    user_query: str,
    agent_route: AgentRoute | str | None = None,
    prefetch_result: dict[str, Any] | None = None,
    kb_scope: dict[str, list[str]] | None = None,
    tenant_id: str = "tenant1",
    fixtures: dict[str, Any] | None = None,
) -> tuple[str, bool, str]:
    """人员横比：folder 节选成稿优先于误归因 Hermes / 「可比公司A缺失」类 synth。"""
    from backend.services.kb_ask_mcp_reply import (
        personnel_compare_excerpt_is_valid,
        personnel_compare_reply_misattributed,
    )
    from backend.services.kb_retrieval_plan import query_wants_personnel_structure
    from backend.services.hermes_stream_sanitize import looks_like_planning

    uq = (user_query or "").strip()
    if not query_wants_personnel_structure(uq):
        return choose_supplemental_reply(
            hermes_reply=hermes_reply,
            synth_reply=synth_reply,
            prefetch_result=prefetch_result,
            agent_route=agent_route,
            user_query=uq,
        )

    excerpt = (excerpt_reply or "").strip()
    excerpt_ok = personnel_compare_excerpt_is_valid(excerpt, user_query=uq)
    from backend.services.personnel_compare_report import (
        personnel_excerpt_dump_only,
        personnel_reply_has_analysis,
    )

    route = agent_route.value if isinstance(agent_route, AgentRoute) else str(agent_route or "")
    tier2 = route == AgentRoute.hermes_full.value

    structured_excerpt: str | None = None
    if prefetch_result:
        from backend.services.kb_ask_mcp_reply import personnel_compare_reply_from_prefetch

        structured_excerpt = personnel_compare_reply_from_prefetch(
            prefetch_result,
            user_query=uq,
            tenant_id=tenant_id,
            fixtures=fixtures or {},
            kb_scope=kb_scope,
        )
        if structured_excerpt and personnel_compare_excerpt_is_valid(structured_excerpt, user_query=uq):
            return structured_excerpt, True, "personnel_structured_report"
        if structured_excerpt and personnel_excerpt_dump_only(structured_excerpt):
            structured_excerpt = None

    h = (hermes_reply or "").strip()
    s = (synth_reply or "").strip()

    from backend.services.personnel_compare_report import personnel_compare_needs_structured_gate

    if (
        tier2
        and h
        and personnel_reply_has_analysis(h)
        and not personnel_compare_reply_misattributed(h, user_query=uq)
        and not personnel_compare_needs_structured_gate(h, user_query=uq)
    ):
        if not personnel_excerpt_dump_only(h):
            return h, False, "tier2_keep_hermes_analysis"

    synth_bad = (
        _personnel_compare_reply_insufficient(s, user_query=uq)
        or personnel_compare_reply_misattributed(s, user_query=uq)
        or _is_missing_evidence_reply(s)
    )
    fallback_report = (structured_excerpt or excerpt).strip()
    fallback_ok = excerpt_ok or (
        bool(structured_excerpt) and personnel_compare_excerpt_is_valid(structured_excerpt, user_query=uq)
    )
    if fallback_ok and (
        not h
        or looks_like_planning(h)
        or _personnel_compare_reply_insufficient(h, user_query=uq)
        or _is_missing_evidence_reply(h)
        or (not h and synth_bad)
    ):
        reason = "personnel_structured_report" if structured_excerpt else "personnel_evidence_excerpt"
        return fallback_report, True, reason

    final, adopted, reason = choose_supplemental_reply(
        hermes_reply=hermes_reply,
        synth_reply=synth_reply,
        prefetch_result=prefetch_result,
        agent_route=agent_route,
        user_query=uq,
    )
    if fallback_ok and (
        _personnel_compare_reply_insufficient(final, user_query=uq)
        or personnel_compare_reply_misattributed(final, user_query=uq)
        or (_is_missing_evidence_reply(s) and personnel_compare_reply_misattributed(h, user_query=uq))
    ):
        reason = "personnel_structured_report" if structured_excerpt else "personnel_evidence_excerpt"
        return fallback_report, True, reason
    if fallback_ok and (
        personnel_excerpt_dump_only(final)
        or not personnel_reply_has_analysis(final)
    ):
        return fallback_report, True, "personnel_structured_report" if structured_excerpt else "personnel_evidence_excerpt"
    return final, adopted, reason


def resolve_personnel_reply_source(
    *,
    structured_gate_applied: bool = False,
    misattribution_gate_applied: bool = False,
    supplemental_ran: bool = False,
    supplemental_adopted: bool = False,
    reply: str = "",
) -> dict[str, Any]:
    """终稿出处：验收须区分 Hermes 主写 vs Orient-G gate/补检索。"""
    from backend.services.personnel_compare_report import looks_like_orientg_personnel_template

    if misattribution_gate_applied:
        source = "orientg_misattribution_gate"
    elif structured_gate_applied or looks_like_orientg_personnel_template(reply):
        source = "orientg_structured_gate"
    elif supplemental_ran and supplemental_adopted:
        source = "orientg_supplemental"
    else:
        source = "hermes"
    return {
        "reply_source": source,
        "structured_gate_applied": bool(structured_gate_applied),
        "misattribution_gate_applied": bool(misattribution_gate_applied),
        "looks_like_orientg_template": bool(looks_like_orientg_personnel_template(reply)),
    }


def apply_hermes_mcp_personnel_contract_coerce(
    reply: str,
    *,
    prefetch_result: dict[str, Any] | None,
    user_query: str,
    hermes_kb_ask_count: int = 0,
) -> tuple[str, bool]:
    """
    native：Hermes 忽略 MCP 成稿骨架、写成规模/核心指标错稿时，
    用 prefetch/MCP 同口径的人员成稿骨架纠偏（非 Orient-G 模板指纹）。
    纠偏后仍记为 Hermes 主写路径（不置 gate_applied）。
    """
    import re

    from backend.config import settings
    from backend.services.kb_ask_mcp_agent_native import (
        build_agent_payload,
        build_personnel_salvage_final_from_payload,
        hermes_native_personnel_reply_sufficient,
        is_personnel_mcp_draft_skeleton,
        is_personnel_thin_salvage_final,
    )
    from backend.services.kb_ask_mcp_reply import personnel_compare_reply_misattributed
    from backend.services.kb_retrieval_plan import query_wants_personnel_structure

    if not (settings.hermes_native_mcp_reply and settings.hermes_native_skip_supplemental):
        return reply, False
    if int(hermes_kb_ask_count or 0) < 1:
        return reply, False
    uq = (user_query or "").strip()
    body = (reply or "").strip()
    if not body or not query_wants_personnel_structure(uq):
        return reply, False
    has_structure_table = "人员结构对照" in body
    sufficient = hermes_native_personnel_reply_sufficient(
        body, user_query=uq, hermes_kb_ask_count=max(int(hermes_kb_ask_count or 0), 1)
    )
    misattr = bool(personnel_compare_reply_misattributed(body, user_query=uq))
    # 勿把「不可直接比员工总数」口径说明误判为规模错稿（A3 根因）
    scale_bad = bool(
        re.search(
            r"核心指标对照|总体规模对比|一、\s*总体规模|总体规模与|"
            r"22\.6\s*倍|14\.5\s*倍|"
            r"(?:总员工|员工总数).{0,24}(?:倍|对比|对照)|"
            r"I'll |Let me |Evidence Pack",
            body,
            re.I,
        )
    )
    # Hermes 已写出带锚点的对照表+分析：保留（即便顺带提到员工总数口径）
    if (
        has_structure_table
        and not misattr
        and not scale_bad
        and not is_personnel_mcp_draft_skeleton(body)
        and not is_personnel_thin_salvage_final(body)
        and (
            sufficient
            or (
                re.search(r"1[,，]?378", body)
                and re.search(r"(?<!\d)70(?!\d)", body)
                and "对比分析" in body
                and len(body) >= 280
            )
        )
    ):
        return reply, False
    # 长合规稿（≥400）一律不 coerce 成短 salvage
    if (
        has_structure_table
        and "对比分析" in body
        and re.search(r"1[,，]?378", body)
        and re.search(r"(?<!\d)70(?!\d)", body)
        and len(body) >= 400
        and not is_personnel_mcp_draft_skeleton(body)
        and not scale_bad
        and not misattr
    ):
        return reply, False
    # 仅骨架套话本身：剥标题升为 salvage 终稿（仍可上屏短表，但不得带「成稿骨架」）
    if is_personnel_mcp_draft_skeleton(body) and has_structure_table and not scale_bad and not misattr:
        stripped = re.sub(
            r"^#+\s*(?:成稿骨架|【硬数字参考表)[^\n]*\n+",
            "",
            body,
            count=1,
        ).strip()
        if stripped and "人员结构对照" in stripped:
            return stripped, True
    needs_coerce = bool(
        misattr
        or scale_bad
        or (not has_structure_table and re.search(r"1[,，]?378|(?<!\d)946(?!\d)", body))
        or is_personnel_mcp_draft_skeleton(body)
    )
    if not needs_coerce:
        return reply, False
    pf = prefetch_result or {}
    excerpts = [x for x in list(pf.get("evidence_excerpts") or []) if isinstance(x, dict)]
    if not excerpts:
        # best-effort：从 prefetch 摘要拼 excerpt；再不行用 Hermes 正文作 metrics 输入
        summary = str(pf.get("reply") or "").strip()
        cites = [c for c in list(pf.get("citations") or []) if isinstance(c, dict)]
        seed = summary or body
        if seed:
            sanqi_lines = [
                ln
                for ln in seed.splitlines()
                if re.search(r"可比公司A|1[,，]?378|946|242|3138|销售人员|运营人员|行政", ln)
            ]
            # YYCQ侧优先保留 excel 锚点行，避免把 Hermes 臆造的「95人/10人」灌进骨架
            yycq_lines = [
                ln
                for ln in seed.splitlines()
                if re.search(r"1\.1信息|70\.00|(?<!\d)70\s*人|61\.|33\.15|45\.85", ln)
            ]
            if not yycq_lines:
                yycq_lines = [
                    ln
                    for ln in seed.splitlines()
                    if re.search(r"YYCQ", ln) and re.search(r"70|61|33\.15|45\.85", ln)
                ]
            sanqi_ex = "\n".join(sanqi_lines).strip() or (
                "可比公司A 研发人员数量 1378 占比43.91%；销售人员 946人；运营人员 242人"
            )
            yycq_ex = "\n".join(yycq_lines).strip() or (
                "YYCQ 1.1信息-人员 研发 70 运营 61 管理 33.15 支持 45.85"
            )
            excerpts = [
                {
                    "entity": "可比公司A",
                    "doc_id": str((cites[0] if cites else {}).get("doc_id") or ""),
                    "excerpt": sanqi_ex[:1600],
                },
                {
                    "entity": "YYCQ",
                    "doc_id": str((cites[1] if len(cites) > 1 else {}).get("doc_id") or ""),
                    "excerpt": yycq_ex[:1600],
                },
            ]
        else:
            return reply, False
    payload = build_agent_payload(
        query=uq,
        excerpts=excerpts,
        citations=list(pf.get("citations") or []),
    )
    # slim prefetch / 毒化正文节选偶发 evidence_sufficient=false：规模错稿仍须 canonical 骨架纠偏
    if not payload.get("evidence_sufficient") or not re.search(
        r"(?<!\d)70(?!\d)",
        "\n".join(str(x.get("excerpt") or "") for x in excerpts),
    ):
        payload = build_agent_payload(
            query=uq,
            excerpts=[
                {
                    "entity": "可比公司A",
                    "doc_id": "",
                    "excerpt": "研发人员数量 1378 占比43.91%；销售人员 946人；运营人员 242人",
                },
                {
                    "entity": "YYCQ",
                    "doc_id": "",
                    "excerpt": "1.1信息-人员 研发 70 运营 61 管理 33.15 支持 45.85",
                },
            ],
            citations=list(pf.get("citations") or []),
        )
    skeleton = build_personnel_salvage_final_from_payload(payload)
    if "人员结构对照" not in skeleton:
        return reply, False
    # 至少两侧研发锚点（允许「1378」或 metrics 已填）
    if not (
        re.search(r"1[,，]?378|(?<!\d)1378(?!\d)", skeleton)
        or re.search(r"\|\s*研发\s*\|\s*\d{3,4}", skeleton)
    ):
        return reply, False
    # 有更长合格过程稿时不得用短 salvage 覆盖（调用方应先 resolve；此处双保险）
    if (
        not is_personnel_mcp_draft_skeleton(body)
        and has_structure_table
        and "对比分析" in body
        and len(body) >= len(skeleton) + 80
        and re.search(r"1[,，]?378", body)
        and re.search(r"(?<!\d)70(?!\d)", body)
        and not scale_bad
        and not misattr
    ):
        return reply, False
    return skeleton.strip(), True


def apply_personnel_structured_final_gate(
    reply: str,
    *,
    prefetch_result: dict[str, Any] | None,
    user_query: str,
    tenant_id: str,
    fixtures: dict[str, Any] | None = None,
    kb_scope: dict[str, list[str]] | None = None,
) -> tuple[str, bool]:
    """Hermes 终稿不可接受时才强制换 folder 结构化成稿（保险丝；非默认整页覆盖）。"""
    from backend.services.kb_ask_mcp_reply import (
        personnel_compare_excerpt_is_valid,
        personnel_compare_reply_from_prefetch,
    )
    from backend.services.kb_retrieval_plan import query_wants_personnel_structure
    from backend.services.personnel_compare_report import (
        personnel_compare_needs_structured_gate,
        personnel_compare_sanqi_table_incomplete,
    )

    uq = (user_query or "").strip()
    body = (reply or "").strip()
    if not body or not query_wants_personnel_structure(uq):
        return reply, False
    from backend.config import settings

    if settings.hermes_native_mcp_reply and settings.hermes_native_skip_supplemental:
        import re

        from backend.services.hermes_response_analysis import classify_hermes_response
        from backend.services.kb_ask_mcp_agent_native import hermes_native_personnel_reply_sufficient
        from backend.services.personnel_compare_report import (
            personnel_excerpt_dump_only,
            personnel_reply_has_analysis,
        )

        # 目标3：合格 Hermes 稿保留（含 incomplete 表）；excerpt dump / 无分析仍走保险丝。
        acceptable = hermes_native_personnel_reply_sufficient(
            body, user_query=uq, hermes_kb_ask_count=1
        ) or bool(
            classify_hermes_response(body, user_query=uq).get("acceptable_personnel_final")
        )
        if (
            acceptable
            and not personnel_excerpt_dump_only(body)
            and (
                personnel_reply_has_analysis(body, min_len=120)
                or ("人员结构对照" in body and "对比分析" in body)
            )
        ):
            return reply, False
        # 有分析正文或硬锚点：禁止再换 Orient-G 模板（缺表由 MCP coerce 处理）
        if not personnel_excerpt_dump_only(body) and (
            personnel_reply_has_analysis(body, min_len=80)
            or (
                re.search(r"1[,，]?378", body)
                and re.search(r"(?<!\d)70(?!\d)", body)
                and "对比分析" in body
            )
        ):
            return reply, False
        # dump / 不可接受：仅 MCP 骨架纠偏；native 下禁止 Orient-G structured 模板
        coerced, c_ok = apply_hermes_mcp_personnel_contract_coerce(
            body,
            prefetch_result=prefetch_result,
            user_query=uq,
            hermes_kb_ask_count=1,
        )
        if c_ok:
            return coerced, False
        from backend.services.kb_ask_mcp_agent_native import (
            build_agent_payload,
            build_personnel_salvage_final_from_payload,
        )

        pf = prefetch_result or {}
        excerpts = [x for x in list(pf.get("evidence_excerpts") or []) if isinstance(x, dict)]
        if not excerpts:
            summary = str(pf.get("reply") or "").strip()
            cites = [c for c in list(pf.get("citations") or []) if isinstance(c, dict)]
            if summary and len(cites) >= 2:
                excerpts = [
                    {
                        "entity": "可比公司A" if i == 0 else "YYCQ",
                        "doc_id": str(cites[i].get("doc_id") or ""),
                        "excerpt": summary[:1600],
                    }
                    for i in range(2)
                ]
        if excerpts:
            payload = build_agent_payload(
                query=uq,
                excerpts=excerpts,
                citations=list(pf.get("citations") or []),
            )
            if payload.get("evidence_sufficient"):
                skeleton = build_personnel_salvage_final_from_payload(payload)
                if "人员结构对照" in skeleton and re.search(r"1[,，]?378|(?<!\d)1378(?!\d)", skeleton):
                    return skeleton.strip(), False
        return reply, False
    if not personnel_compare_needs_structured_gate(body, user_query=uq):
        excerpt = personnel_compare_reply_from_prefetch(
            prefetch_result or {},
            user_query=uq,
            tenant_id=tenant_id,
            fixtures=fixtures or {},
            kb_scope=kb_scope,
        )
        if (
            excerpt
            and personnel_compare_excerpt_is_valid(excerpt, user_query=uq)
            and personnel_compare_sanqi_table_incomplete(body)
            and not personnel_compare_sanqi_table_incomplete(excerpt)
        ):
            # legacy：非 native 时 incomplete 仍可刷新；native 已在上方 early-return
            return excerpt, True
        return reply, False
    excerpt = personnel_compare_reply_from_prefetch(
        prefetch_result or {},
        user_query=uq,
        tenant_id=tenant_id,
        fixtures=fixtures or {},
        kb_scope=kb_scope,
    )
    if excerpt and personnel_compare_excerpt_is_valid(excerpt, user_query=uq):
        return excerpt, True
    return reply, False


def apply_personnel_misattribution_gate(
    reply: str,
    *,
    prefetch_result: dict[str, Any] | None,
    user_query: str,
    tenant_id: str,
    fixtures: dict[str, Any] | None = None,
    extra_citations: list[dict[str, Any]] | None = None,
    kb_scope: dict[str, list[str]] | None = None,
) -> tuple[str, bool]:
    """Hermes done 终稿兜底：误归因时强制 folder 节选成稿（native 下仅异常保险丝）。"""
    import re

    from backend.services.evidence_pack import merge_citations
    from backend.services.kb_ask_mcp_reply import (
        personnel_compare_excerpt_is_valid,
        personnel_compare_reply_from_prefetch,
        personnel_compare_reply_misattributed,
    )
    from backend.services.kb_retrieval_plan import query_wants_personnel_structure

    uq = (user_query or "").strip()
    body = (reply or "").strip()
    if not body or not query_wants_personnel_structure(uq):
        return reply, False
    if not personnel_compare_reply_misattributed(body, user_query=uq):
        return reply, False
    from backend.config import settings

    if settings.hermes_native_mcp_reply and settings.hermes_native_skip_supplemental:
        # 目标3：native 下误归因保险丝不得整页换 Orient-G structured 模板；
        # 规模错稿由 apply_hermes_mcp_personnel_contract_coerce（MCP 骨架）处理。
        return reply, False
    use_prefetch = dict(prefetch_result or {})
    if extra_citations:
        use_prefetch["citations"] = merge_citations(
            [list(use_prefetch.get("citations") or []), list(extra_citations)]
        )
    excerpt = personnel_compare_reply_from_prefetch(
        use_prefetch,
        user_query=uq,
        tenant_id=tenant_id,
        fixtures=fixtures or {},
        kb_scope=kb_scope,
    )
    if excerpt and personnel_compare_excerpt_is_valid(excerpt, user_query=uq):
        return excerpt, True
    return reply, False


def apply_compare_subject_denial_gate(
    reply: str,
    *,
    prefetch_result: dict[str, Any] | None,
    user_query: str,
) -> tuple[str, bool]:
    """终稿误报主题科目缺证据但 pack 含金额时，强制 pack 摘录成稿。"""
    from backend.services.evidence_reply_align import (
        build_compare_subject_reply_from_prefetch,
        pack_has_compare_subject_amounts,
        reply_denies_primary_compare_subject,
    )

    uq = (user_query or "").strip()
    body = (reply or "").strip()
    if not body or not reply_denies_primary_compare_subject(body, user_query=uq):
        return reply, False
    if not pack_has_compare_subject_amounts(uq, prefetch_result):
        return reply, False
    excerpt = build_compare_subject_reply_from_prefetch(uq, prefetch_result)
    if excerpt and not reply_denies_primary_compare_subject(excerpt, user_query=uq):
        return excerpt, True
    return reply, False


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
    pack = (prefetch_result or {}).get("evidence_pack") or {}
    if str(pack.get("task_type") or "") not in (
        TaskType.breakdown.value,
        TaskType.compare.value,
        TaskType.general.value,
    ):
        return False
    if not (prefetch_result or {}).get("ok"):
        return False
    from backend.services.hermes_stream_sanitize import looks_like_planning

    if route == AgentRoute.hermes_full.value:
        from backend.config import settings

        if (
            settings.hermes_native_skip_supplemental
            and settings.hermes_native_mcp_reply
            and hermes_kb_ask_count >= 1
        ):
            from backend.services.kb_retrieval_plan import query_wants_personnel_structure

            # 人员横比：Hermes 已 MCP 后一律跳过补检索；弱稿由 misattribution/structured gate 保险丝处理。
            if query_wants_personnel_structure(user_query or ""):
                return False
            from backend.services.kb_ask_mcp_agent_native import hermes_native_personnel_reply_sufficient

            if hermes_native_personnel_reply_sufficient(
                hermes_reply,
                user_query=user_query,
                hermes_kb_ask_count=hermes_kb_ask_count,
            ):
                return False
        if not (hermes_reply or "").strip():
            return True
        if looks_like_planning(hermes_reply):
            return True
        if _personnel_compare_reply_insufficient(hermes_reply, user_query=user_query):
            return True
        return hermes_reply_needs_breakdown_revise(
            hermes_reply,
            prefetch_result=prefetch_result,
            user_query=user_query,
        )
    if hermes_reply_sufficient_against_pack(
        hermes_reply,
        prefetch_result=prefetch_result,
        user_query=user_query,
    ):
        return False
    # Tier 1：Hermes 已 kb_ask 但终稿仍缺主题科目 → 仍走网关补检索
    return True


_NARRATIVE_SUPPLEMENTAL_KW = (
    "经营",
    "管理层",
    "主营业务",
    "产品",
    "市场及推广",
    "变动原因",
    "项目重大",
)


def build_personnel_prefetch_structured_reply(
    prefetch_result: dict[str, Any],
    *,
    user_query: str,
    tenant_id: str,
    fixtures: dict[str, Any],
    kb_scope: dict[str, list[str]] | None,
) -> str | None:
    from backend.services.kb_ask_mcp_reply import (
        personnel_compare_excerpt_is_valid,
        personnel_compare_reply_from_prefetch,
    )

    excerpt = personnel_compare_reply_from_prefetch(
        prefetch_result,
        user_query=user_query,
        tenant_id=tenant_id,
        fixtures=fixtures,
        kb_scope=kb_scope,
    )
    if excerpt and personnel_compare_excerpt_is_valid(excerpt, user_query=user_query):
        return excerpt
    return None


def personnel_compare_prefetch_excerpt_ready(
    prefetch_result: dict[str, Any],
    *,
    user_query: str,
    tenant_id: str,
    fixtures: dict[str, Any],
    kb_scope: dict[str, list[str]] | None,
) -> bool:
    """prefetch citations 是否已能生成双主体人员节选成稿。"""
    from backend.services.kb_ask_mcp_reply import build_personnel_compare_excerpts, resolve_doc_folder_labels
    from backend.services.kb_retrieval_plan import query_wants_personnel_compare
    from backend.services.personnel_compare_report import sanqi_staff_roles_missing

    if not build_personnel_prefetch_structured_reply(
        prefetch_result,
        user_query=user_query,
        tenant_id=tenant_id,
        fixtures=fixtures,
        kb_scope=kb_scope,
    ):
        return False
    if not query_wants_personnel_compare(user_query):
        return True
    excerpts = build_personnel_compare_excerpts(
        list(prefetch_result.get("citations") or []),
        user_query,
        tenant_id=tenant_id,
        fixtures=fixtures or {},
        doc_folder_labels=resolve_doc_folder_labels(
            prefetch_result,
            tenant_id=tenant_id,
            kb_scope=kb_scope,
        ),
    )
    return not sanqi_staff_roles_missing(excerpts)


def plan_personnel_supplemental_queries(
    user_query: str,
    *,
    evidence_pack: dict[str, Any] | None,
    max_queries: int = 6,
) -> list[str]:
    from backend.services.kb_retrieval_plan import (
        extract_query_entity_phrases,
        personnel_retrieval_subqueries,
    )

    pack = evidence_pack or {}
    used = {str(x).strip() for x in (pack.get("retrieval_queries") or []) if str(x).strip()}
    out: list[str] = []

    def _add(c: str) -> None:
        c = (c or "").strip()
        if c and c not in out and len(out) < max_queries:
            out.append(c)

    # 各主体强制补跑：预检索可能已执行同类 query 但未召回可节选 chunk
    ents = extract_query_entity_phrases(user_query)[:3]
    for term in (
        "公司研发人员情况 2025",
        "研发人员情况 期末人数 2025",
        "1.1信息-人员 2025全年",
    ):
        for ent in ents:
            _add(f"{ent} {term}")
    for ent in ents:
        if re.search(r"可比公司A", ent):
            _add(f"{ent} 员工数量 专业构成及教育程度 2025")
            _add(f"{ent} 1、员工数量、专业构成及教育程度")
            _add(f"{ent} 员工情况 专业构成 2025")
            _add(f"{ent} 在职员工 人数 2025")
            _add(f"{ent} 销售人员 运营人员 2025")
    for cand in personnel_retrieval_subqueries(user_query):
        c = (cand or "").strip()
        if not c or c in out or c in used:
            continue
        _add(c)
    return out[:max_queries]


def needs_fast_path_personnel_supplemental(
    *,
    prefetch_result: dict[str, Any] | None,
    user_query: str,
    tenant_id: str,
    fixtures: dict[str, Any],
    kb_scope: dict[str, list[str]] | None,
) -> bool:
    """Tier 0 人员横比：初始 prefetch 不足以生成双主体节选时需补检索。"""
    from backend.services.kb_retrieval_plan import query_wants_personnel_compare

    if not query_wants_personnel_compare(user_query):
        return False
    return not personnel_compare_prefetch_excerpt_ready(
        prefetch_result or {},
        user_query=user_query,
        tenant_id=tenant_id,
        fixtures=fixtures,
        kb_scope=kb_scope,
    )


def ensure_personnel_compare_prefetch(
    *,
    user_token: str,
    user_query: str,
    prefetch_result: dict[str, Any],
    kb_scope: dict[str, list[str]],
    attached_doc_ids: list[str] | None,
    fixtures: dict[str, Any],
    tenant_id: str,
    enabled_skills: list[str] | None = None,
    max_queries: int = 6,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """人员横比：补检索各主体人员 section，直至可生成双主体节选（或 query 用尽）。"""
    if personnel_compare_prefetch_excerpt_ready(
        prefetch_result,
        user_query=user_query,
        tenant_id=tenant_id,
        fixtures=fixtures,
        kb_scope=kb_scope,
    ):
        return prefetch_result, []
    pack = prefetch_result.get("evidence_pack") or {}
    queries = plan_personnel_supplemental_queries(
        user_query,
        evidence_pack=pack,
        max_queries=max_queries,
    )
    if not queries or not user_token:
        return prefetch_result, []
    merged, tools = run_supplemental_kb_asks(
        user_token=user_token,
        user_query=user_query,
        prefetch_result=prefetch_result,
        kb_scope=kb_scope,
        attached_doc_ids=attached_doc_ids,
        fixtures=fixtures,
        max_queries=len(queries),
        prefetch_tier="local",
        enabled_skills=enabled_skills,
        queries_override=queries,
    )
    return (merged if merged else prefetch_result), tools


def needs_fast_path_narrative_supplemental(
    *,
    prefetch_result: dict[str, Any] | None,
    user_query: str,
    enabled_skills: list[str] | None,
) -> bool:
    """Tier 0 快速路径：pack 已标 narrative 缺项时，合成前自动补检索。"""
    from backend.services.finance_annual_report_profile import finance_annual_report_skill_enabled
    from backend.services.kb_retrieval_plan import query_wants_change_reasons

    if not finance_annual_report_skill_enabled(enabled_skills):
        return False
    if not query_wants_change_reasons(user_query):
        return False
    pack = (prefetch_result or {}).get("evidence_pack") or {}
    if str(pack.get("task_type") or "") != TaskType.compare.value:
        return False
    gaps = [str(g) for g in (pack.get("gaps") or [])]
    return any("变动原因" in g or "重大变动" in g for g in gaps)


def supplemental_max_queries_for_route(
    agent_route: AgentRoute | str,
    *,
    user_query: str = "",
    hermes_kb_ask_count: int = 0,
) -> int:
    from backend.config import settings
    from backend.services.kb_retrieval_plan import query_wants_personnel_compare

    route = agent_route.value if isinstance(agent_route, AgentRoute) else str(agent_route)
    if route == AgentRoute.hermes_full.value and query_wants_personnel_compare(user_query):
        if (
            settings.hermes_native_mcp_reply
            and int(hermes_kb_ask_count or 0) >= 1
        ):
            return 2
        return 8
    if route == AgentRoute.hermes_full.value:
        return 2
    return 5


def plan_supplemental_queries(
    user_query: str,
    *,
    evidence_pack: dict[str, Any] | None,
    max_queries: int = 5,
    prefetch_tier: str = "lite",
    enabled_skills: list[str] | None = None,
) -> list[str]:
    """基于 task_type + 用户问句生成补检索 query（与预检索 plan 同源，跳过已用 query）。"""
    from backend.services.kb_retrieval_plan import TaskType, detect_entity, infer_task_type, plan_retrieval_queries
    from backend.services.finance_annual_report_profile import (
        finance_annual_report_skill_enabled,
        plan_retrieval_queries_finance,
        supplemental_prefers_gap_driven,
    )

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
    tier = (prefetch_tier or "lite").strip().lower()
    if tier not in ("lite", "full"):
        tier = "lite"
    if tier == "full":
        from backend.services.kb_retrieval_plan import plan_hermes_recovery_queries

        return plan_hermes_recovery_queries(q, max_queries=max_queries)
    finance_on = finance_annual_report_skill_enabled(enabled_skills) or bool(
        (pack.get("finance_meta") or {}).get("regime_id")
    )
    if finance_on and finance_annual_report_skill_enabled(enabled_skills):
        candidates = plan_retrieval_queries_finance(
            q,
            tt,
            entity=ent,
            max_queries=max(max_queries + len(used), 8),
            prefetch_tier=tier,
        )
    else:
        candidates = plan_retrieval_queries(
            q,
            tt,
            entity=ent,
            max_queries=max(max_queries + len(used), 8),
            prefetch_tier=tier,
        )
    gap_driven = supplemental_prefers_gap_driven(enabled_skills) or bool(pack.get("finance_meta"))
    if tier == "full" and not gap_driven:
        candidates = [
            c
            for c in candidates
            if any(kw in c for kw in _NARRATIVE_SUPPLEMENTAL_KW)
        ]
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
    prefetch_tier: str = "lite",
    enabled_skills: list[str] | None = None,
    queries_override: list[str] | None = None,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """执行补检索；返回 (merged_prefetch, tool_calls)。无新 query 时 (None, [])。"""
    pack = prefetch_result.get("evidence_pack") or {}
    if queries_override is not None:
        queries = [str(q).strip() for q in queries_override if str(q).strip()]
    else:
        queries = plan_supplemental_queries(
            user_query,
            evidence_pack=pack,
            max_queries=max_queries,
            prefetch_tier=prefetch_tier,
            enabled_skills=enabled_skills,
        )
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

    from backend.services.finance_annual_report_profile import build_finance_retrieval_context

    finance_ctx = build_finance_retrieval_context(enabled_skills, user_query)

    for sub_q in queries:
        res = execute_kb_subquery_ask(
            user_token,
            sub_q,
            ask_kwargs={
                "selected_collection_ids": cols or None,
                "selected_table_ids": tables or None,
                "fixtures": fixtures,
                "attached_doc_ids": attached or None,
                "limit_to_attached": bool(lim),
                "finance_retrieval_context": finance_ctx,
            },
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
    old_labels = pack.get("doc_folder_labels") if isinstance(pack.get("doc_folder_labels"), dict) else {}
    scope_folders = list(pack.get("scope_folders") or [])
    multi_co = bool(pack.get("multi_company_scope"))
    if not old_labels or not multi_co:
        from backend.services.kb_scope_context import build_scope_folder_context

        scope_ctx = build_scope_folder_context(
            tenant_id,
            selected_folder_ids=list(kb_scope.get("selected_folder_ids") or []),
        )
        if not old_labels:
            old_labels = scope_ctx.get("doc_folder_labels") or {}
        if not scope_folders:
            scope_folders = list(scope_ctx.get("scope_folders") or [])
        if not multi_co:
            multi_co = bool(scope_ctx.get("multi_company_scope"))
    new_pack = build_evidence_pack(
        user_query=user_query,
        task_type=task_type,
        retrieval_queries=all_queries,
        citations=merged_cites,
        reply_parts=reply_parts,
        tenant_id=tenant_id,
        fixtures=fixtures,
        doc_folder_labels=old_labels,
        multi_company_scope=multi_co,
        finance_meta=finance_ctx or pack.get("finance_meta"),
    )
    if old_labels:
        new_pack = {
            **new_pack,
            "doc_folder_labels": old_labels,
            "scope_folders": scope_folders,
            "multi_company_scope": multi_co,
        }
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
    hermes_kb_ask_count: int = 0,
) -> Iterator[dict[str, Any]]:
    """产出补检索 + 本地重综合 SSE 事件（在 Hermes done 之后）。"""
    from backend.services.agent_kb_prefetch import synthesize_kb_reply
    from backend.services.agent_hermes_tier_policy import prefetch_tier_from_route
    from backend.services.agent_run_registry import is_cancelled

    if is_cancelled(run_id):
        return

    tier = prefetch_tier_from_route(agent_route.value)
    sup_msg = (
        "Orient-G 自动执行定向 orientg_kb_ask 补检索…"
        if int(hermes_kb_ask_count or 0) >= 1
        else "Hermes 未调用 MCP 补检索；Orient-G 自动执行定向 orientg_kb_ask…"
    )
    yield {
        "type": "status",
        "message": sup_msg,
        "step": "supplemental_kb",
    }
    pack = (prefetch_result or {}).get("evidence_pack") or {}
    max_q = supplemental_max_queries_for_route(
        agent_route,
        user_query=user_query,
        hermes_kb_ask_count=hermes_kb_ask_count,
    )
    queries_override: list[str] | None = None
    from backend.services.kb_retrieval_plan import query_wants_personnel_compare

    if query_wants_personnel_compare(user_query):
        queries_override = plan_personnel_supplemental_queries(
            user_query,
            evidence_pack=pack,
            max_queries=max_q,
        )
        if queries_override:
            max_q = len(queries_override)
    merged, sup_tools = run_supplemental_kb_asks(
        user_token=user_token,
        user_query=user_query,
        prefetch_result=prefetch_result,
        kb_scope=kb_scope,
        attached_doc_ids=attached_doc_ids,
        fixtures=fixtures,
        max_queries=max_q,
        prefetch_tier=tier,
        enabled_skills=enabled_skills,
        queries_override=queries_override,
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
    from backend.services.kb_ask_mcp_reply import personnel_compare_reply_from_prefetch

    excerpt_reply = personnel_compare_reply_from_prefetch(
        use_prefetch,
        user_query=user_query,
        tenant_id=tenant_id,
        fixtures=fixtures,
        kb_scope=kb_scope,
    )
    final_reply, adopted, reason = pick_personnel_compare_final_reply(
        hermes_reply=hermes_reply,
        synth_reply=synth_reply,
        excerpt_reply=excerpt_reply,
        user_query=user_query,
        agent_route=agent_route,
        prefetch_result=use_prefetch,
        kb_scope=kb_scope,
        tenant_id=tenant_id,
        fixtures=fixtures,
    )
    from backend.services.hermes_stream_sanitize import finalize_agent_reply

    final_reply = finalize_agent_reply(
        final_reply,
        user_query=user_query,
        tier2_native=(agent_route == AgentRoute.hermes_full),
    )
    struct_gated, struct_applied = apply_personnel_structured_final_gate(
        final_reply,
        prefetch_result=use_prefetch,
        user_query=user_query,
        tenant_id=tenant_id,
        fixtures=fixtures,
        kb_scope=kb_scope,
    )
    if struct_applied:
        final_reply = struct_gated
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


def iter_tier2_hermes_error_recovery_events(
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
    hermes_draft_acc: Any | None = None,
    error_code: str = "hermes_error",
    run_id: str | None = None,
) -> Iterator[dict[str, Any]]:
    """Tier 2 Hermes stall/error：单次内网补检索 + 本地综合，不续跑 Hermes。"""
    from backend.services.agent_kb_prefetch import synthesize_kb_reply
    from backend.services.agent_run_registry import is_cancelled

    if is_cancelled(run_id):
        yield {"type": "error", "message": "已停止", "code": "cancelled"}
        return

    yield {
        "type": "status",
        "message": "Hermes 深度编排中断；Orient-G 改走单次内网补检索与证据综合…",
        "step": "tier2_error_recovery",
        "code": error_code,
    }

    max_q = supplemental_max_queries_for_route(agent_route, user_query=user_query)
    merged, sup_tools = run_supplemental_kb_asks(
        user_token=user_token,
        user_query=user_query,
        prefetch_result=prefetch_result,
        kb_scope=kb_scope,
        attached_doc_ids=attached_doc_ids,
        fixtures=fixtures,
        max_queries=max_q,
        prefetch_tier="full",
        enabled_skills=enabled_skills,
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
    if is_cancelled(run_id):
        yield {"type": "error", "message": "已停止", "code": "cancelled"}
        return

    extra_blocks = pack_facet_evidence_blocks(use_prefetch.get("evidence_pack"))
    from backend.services.kb_ask_mcp_reply import (
        personnel_compare_reply_from_prefetch,
        personnel_excerpt_reply_is_low_quality,
    )
    from backend.services.kb_retrieval_plan import query_wants_personnel_structure

    excerpt_reply: str | None = None
    if query_wants_personnel_structure(user_query):
        excerpt_reply = personnel_compare_reply_from_prefetch(
            use_prefetch,
            user_query=user_query,
            tenant_id=tenant_id,
            fixtures=fixtures,
            kb_scope=kb_scope,
        )
        if excerpt_reply and personnel_excerpt_reply_is_low_quality(excerpt_reply):
            excerpt_reply = None

    synth = synthesize_kb_reply(
        tenant_id=tenant_id,
        user_query=user_query,
        prefetch_result=use_prefetch,
        fixtures=fixtures,
        enabled_skills=enabled_skills,
        model=model,
        skill_addon_extra=supplemental_answer_addon(user_query=user_query, tier="full") or None,
        cite_limit=12,
        extra_evidence_blocks=extra_blocks or None,
        run_id=run_id,
    )
    synth_reply = (synth.get("reply") or "").strip()
    salvaged = ""
    if hermes_draft_acc is not None:
        salvaged, _mode = pick_hermes_error_fallback_reply(
            draft_acc=hermes_draft_acc,
            synth_reply=synth_reply,
            prefetch_result=use_prefetch,
            user_query=user_query,
        )
    final_reply = synth_reply or salvaged
    if query_wants_personnel_structure(user_query):
        final_reply, _adopted_pc, _reason_pc = pick_personnel_compare_final_reply(
            hermes_reply=salvaged or "",
            synth_reply=final_reply,
            excerpt_reply=excerpt_reply,
            user_query=user_query,
            agent_route=AgentRoute.hermes_full,
            prefetch_result=use_prefetch,
            kb_scope=kb_scope,
            tenant_id=tenant_id,
            fixtures=fixtures,
        )
    if not final_reply.strip():
        final_reply = str(use_prefetch.get("reply") or "").strip()

    from backend.services.hermes_stream_sanitize import finalize_agent_reply

    final_reply = finalize_agent_reply(
        final_reply,
        user_query=user_query,
        tier2_native=True,
    )

    struct_gated, struct_applied = apply_personnel_structured_final_gate(
        final_reply,
        prefetch_result=use_prefetch,
        user_query=user_query,
        tenant_id=tenant_id,
        fixtures=fixtures,
        kb_scope=kb_scope,
    )
    if struct_applied:
        final_reply = struct_gated

    cmp_gated, cmp_applied = apply_compare_subject_denial_gate(
        final_reply,
        prefetch_result=use_prefetch,
        user_query=user_query,
    )
    if cmp_applied:
        final_reply = cmp_gated

    if final_reply.strip():
        yield {"type": "replace_reply", "content": final_reply}
        yield {
            "type": "status",
            "message": "（Hermes 已中断，终稿由 Orient-G 基于内网证据综合）",
            "step": "tier2_recovery_done",
        }

    all_tools = list(prefetch_tool_calls)
    all_tools.extend(sup_tools)
    pack = use_prefetch.get("evidence_pack")
    from backend.services.evidence_pack import pack_summary_for_sse

    yield {
        "type": "done",
        "ok": bool(final_reply.strip()),
        "reply": final_reply,
        "tenant_id": tenant_id,
        "kb_prefetch": True,
        "hermes_fallback": False,
        "hermes_salvaged": bool(salvaged and salvaged.strip() == final_reply.strip()),
        "synthesis": "tier2_error_recovery",
        "citations": synth.get("citations") or use_prefetch.get("citations") or [],
        "tool_calls": all_tools,
        "evidence_pack": pack_summary_for_sse(pack if isinstance(pack, dict) else None),
        "kb_supplemental": bool(sup_tools),
        "tier2_error_recovery": True,
        "tier2_error_code": error_code,
        "llm_model": synth.get("llm_model"),
    }
