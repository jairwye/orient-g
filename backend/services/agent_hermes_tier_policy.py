"""Agent 分层策略：local=快速 / lite=标准 / full=深度。"""

from __future__ import annotations

from typing import Any, Literal

PrefetchTier = Literal["local", "lite", "full"]


def prefetch_tier_for_agent_mode(agent_mode: str) -> PrefetchTier:
    """预检索阶段按 UI 模式映射 excerpt / 子 query 档位。"""
    mode = (agent_mode or "standard").strip().lower()
    if mode == "deep":
        return "full"
    if mode == "standard":
        return "lite"
    return "local"


def prefetch_tier_from_route(orientg_route: str | None, *, agent_mode: str = "standard") -> PrefetchTier:
    mode = (agent_mode or "standard").strip().lower()
    route = (orientg_route or "").strip().lower()
    if mode == "deep" or route == "hermes_full":
        return "full"
    if route == "hermes_lite":
        return "lite"
    return prefetch_tier_for_agent_mode(agent_mode)


def prefetch_system_lead(
    *,
    via_hermes: bool,
    evidence_pack: dict[str, Any] | None,
    tier: PrefetchTier,
) -> str:
    """预检索注入 system 首段（由 tier 决定，非用户问句关键词）。"""
    from backend.services.agent_kb_fast_path import prefetch_system_lead as _base_local

    gaps = (evidence_pack or {}).get("gaps") or []
    gap_hint = ""
    if gaps:
        gap_hint = "【缺项】" + "；".join(str(g) for g in gaps[:5]) + "。\n"

    if not via_hermes:
        return _base_local(via_hermes=False, evidence_pack=evidence_pack) + gap_hint

    from backend.services.kb_scope_context import multi_company_scope_addon

    multi_hint = multi_company_scope_addon(evidence_pack)

    if tier == "full":
        return (
            "Orient-G 网关已完成多 query 预检索并生成 Evidence Pack（见 JSON）。\n"
            "【深度编排 · Tier 2 · 分析师报告】请根据用户原话理解交付形态（对比表 vs 分析报告）。\n"
            "1) Evidence Pack 为起点；分析报告类任务成稿前宜 1–2 次 orientg_kb_ask 补经营叙事"
            "（经营情况讨论、主营业务/产品、分项推广策略等），再写终稿。\n"
            "2) 禁止 terminal/shell/自编脚本；允许 orientg_kb_ask / orientg_kb_list。\n"
            "3) 金额须来自证据；解读性段落须标注 doc_id；无证据不得写具体业务故事。\n"
            "4) 禁止复述 Evidence Pack / 内部缺项清单；默认合并利润表口径；"
            "终稿以 `#` 或「结论：」开头。\n"
            + multi_hint
            + gap_hint
        )

    if tier == "lite":
        gap_force = ""
        if gaps:
            gap_force = (
                "4) Evidence Pack 已标注缺项：终稿前**必须**至少 1 次 orientg_kb_ask 针对缺项补检索。\n"
            )
        no_gaps_direct = ""
        if not gaps:
            no_gaps_direct = (
                "0) Evidence Pack **无缺项**且 facets 已含分项金额：须**立即**基于预检索 citations 写完整报告，"
                "禁止 terminal/自编脚本；禁止声称「KB 无数据」或要求用户确认口径。\n"
            )
        return (
            "Orient-G 网关已完成多 query 预检索并生成 Evidence Pack（见 JSON）。\n"
            "【标准编排 · Tier 1 · 合规对比报告】请根据用户原话理解要回答什么。\n"
            + no_gaps_direct
            + "1) 优先 pack.facets；仅针对 gaps 或明显不足再 orientg_kb_ask（预算受限）。\n"
            "2) 禁止 terminal；禁止「估算」「推断」；金额须来自 MCP 或 citations 原文。\n"
            "3) 禁止复述 Evidence Pack；默认合并口径；终稿须分节+Markdown 表+doc 引用。\n"
            + gap_force
            + multi_hint
            + gap_hint
        )

    lead = _base_local(via_hermes=True, evidence_pack=evidence_pack)
    return lead + multi_hint + gap_hint


def discourage_repeat_kb_ask(tier: PrefetchTier) -> bool:
    """快速/标准：预检索已够时少重复 ask；深度不劝阻。"""
    return tier in ("local", "lite")


def hermes_orientg_context_extras(
    *,
    tier: PrefetchTier,
    evidence_pack: dict[str, Any] | None,
    user_query: str = "",
    enabled_skills: list[str] | None = None,
) -> dict[str, Any]:
    from backend.services.agent_kb_supplemental import plan_supplemental_queries
    from backend.services.kb_retrieval_plan import query_wants_analyst_report
    from backend.services.finance_annual_report_profile import (
        finance_annual_report_skill_enabled,
        plan_retrieval_queries_finance,
        supplemental_prefers_gap_driven,
    )

    gaps = [str(g).strip() for g in ((evidence_pack or {}).get("gaps") or []) if str(g).strip()]
    finance_on = finance_annual_report_skill_enabled(enabled_skills) or bool(
        (evidence_pack or {}).get("finance_meta")
    )

    if tier == "lite" and gaps:
        suggested = plan_supplemental_queries(
            user_query,
            evidence_pack=evidence_pack,
            max_queries=3,
            enabled_skills=enabled_skills,
        )
        extras: dict[str, Any] = {
            "orientg_evidence_gaps": gaps[:5],
            "orientg_kb_ask_required": True,
            "orientg_kb_ask_min_calls_before_final_answer": 1,
            "orientg_tool_reminder": (
                "Evidence Pack 仍有缺项；终稿前须至少 1 次 orientg_kb_ask。"
                "禁止 terminal；orientg_kb_* 是唯一合规 KB 通道。"
            ),
        }
        if suggested:
            extras["orientg_suggested_kb_queries"] = suggested
        return extras

    if tier == "full":
        from backend.services.kb_retrieval_plan import (
            TaskType,
            detect_entity,
            infer_task_type,
            plan_retrieval_queries,
        )

        tt = infer_task_type(user_query)
        ent = detect_entity(user_query)
        gap_driven = supplemental_prefers_gap_driven(enabled_skills) or finance_on
        if finance_on and finance_annual_report_skill_enabled(enabled_skills):
            narrative_qs = plan_retrieval_queries_finance(
                user_query,
                tt,
                entity=ent,
                max_queries=6,
                prefetch_tier="full",
            )
        else:
            narrative_qs = plan_retrieval_queries(
                user_query,
                tt,
                entity=ent,
                max_queries=6,
                prefetch_tier="full",
            )
            if not gap_driven:
                narrative_qs = [
                    q
                    for q in narrative_qs
                    if any(k in q for k in ("经营", "管理层", "市场及推广", "主营业务", "销售费用", "附注"))
                ]
        extras: dict[str, Any] = {
            "orientg_tool_reminder": (
                "深度编排：成稿前须 orientg_kb_ask 拉取附注分项与经营叙事（query 与预检索不同）。"
                "禁止 terminal；分项金额须来自 MCP 原文；禁止「约 xx 万」估算。"
            ),
        }
        if gaps:
            extras["orientg_evidence_gaps"] = gaps[:5]
        # breakdown/compare：即使 coverage=100% 也强制至少 1 次 kb_ask（避免单轮 completion 编造分项）
        if tt in (TaskType.breakdown, TaskType.compare):
            extras["orientg_kb_ask_required"] = True
            extras["orientg_kb_ask_min_calls_before_final_answer"] = 1
            extras["orientg_kb_ask_suggested_max"] = 2
            if not narrative_qs:
                narrative_qs = [
                    f"{ent or '华清飞扬'} 2025 2024 销售费用 附注 明细",
                    f"{ent or '华清飞扬'} 销售费用 职工薪酬 市场及推广",
                ]
        elif query_wants_analyst_report(user_query):
            extras["orientg_kb_ask_suggested"] = True
            extras["orientg_kb_ask_suggested_max"] = 2
            if gaps:
                extras["orientg_kb_ask_required"] = True
                extras["orientg_kb_ask_min_calls_before_final_answer"] = 1
        if narrative_qs:
            extras["orientg_suggested_kb_queries"] = narrative_qs[:4]
        if extras.get("orientg_kb_ask_required") or extras.get("orientg_kb_ask_suggested"):
            return extras
        if gaps:
            suggested = plan_supplemental_queries(
                user_query,
                evidence_pack=evidence_pack,
                max_queries=3,
                enabled_skills=enabled_skills,
            )
            extras["orientg_kb_ask_required"] = True
            extras["orientg_kb_ask_min_calls_before_final_answer"] = 1
            if suggested:
                extras["orientg_suggested_kb_queries"] = suggested
            return extras
        return {}

    return {}


def hermes_answer_requirements(*, tier: PrefetchTier, user_query: str) -> str:
    from backend.services.agent_kb_fast_path import comparison_answer_addon
    from backend.services.kb_retrieval_plan import TaskType, infer_task_type

    parts: list[str] = []
    tt = infer_task_type(user_query)

    if tier == "full":
        parts.append(
            "【Orient-G 深度·分析师】终稿须一次性写全；Evidence Pack 不足时 orientg_kb_ask 后再写。"
            "禁止编造分项；无证据则明确缺项。"
        )
        if tt in (TaskType.breakdown, TaskType.compare):
            parts.append(
                "【深度报告结构】须含：结论、核心指标表、分项明细表、分项驱动分析（有 doc 可解读）、"
                "变动原因、盈利能力/费比影响、风险提示（仅证据）、总结、口径说明。"
            )
        cmp = comparison_answer_addon(user_query, tier="full")
        if cmp:
            parts.append(cmp)
    elif tier == "lite":
        parts.append(
            "【Orient-G 标准·合规】Hermes 标准编排；分项金额须来自 citations 或 orientg_kb_ask；"
            "禁止估算/推断；无缺项时立即成稿。"
        )
        if tt in (TaskType.breakdown, TaskType.compare):
            parts.append(
                "【标准报告结构】①结论；②核心指标表；③分项明细表；④变动原因（年报原文）；⑤口径说明。"
            )
        cmp = comparison_answer_addon(user_query, tier="lite")
        if cmp:
            parts.append(cmp)

    return "\n".join(parts).strip()


def patch_prefetch_system_message(
    messages: list[dict[str, str]],
    *,
    orientg_route: str | None,
    evidence_pack: dict[str, Any] | None,
    agent_mode: str = "standard",
    via_hermes: bool = True,
) -> list[dict[str, str]]:
    tier = prefetch_tier_from_route(orientg_route, agent_mode=agent_mode)
    lead = prefetch_system_lead(via_hermes=via_hermes, evidence_pack=evidence_pack, tier=tier)
    out = list(messages or [])
    for i, m in enumerate(out):
        if m.get("role") == "system" and "Orient-G 网关" in str(m.get("content") or ""):
            old = str(m.get("content") or "")
            tail = ""
            if "详情 JSON：" in old:
                tail = old[old.index("详情 JSON：") :]
            elif "引用：" in old:
                tail = old[old.index("引用：") :]
            out[i] = {**m, "content": lead + tail}
            break
    return out


def prefetch_excerpt_limits(tier: PrefetchTier, task_type: str) -> tuple[int, int, int]:
    """(条数, 每条字符上限, max_chunks_per_doc)。"""
    if tier == "full":
        return 8, 8000, 3
    if tier == "lite":
        return 6, 6000, 2
    return 4, 4000, 1
