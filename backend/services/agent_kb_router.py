"""Agent KB 三路分流（映射 Tier 0–2）：fast / hermes_lite / hermes_full。"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any, Literal

AgentMode = Literal["auto", "fast", "standard", "deep"]


class AgentRoute(str, Enum):
    fast = "fast"  # Tier 0：本地证据综合
    hermes_lite = "hermes_lite"  # Tier 1
    hermes_full = "hermes_full"  # Tier 2


_SIMPLE_PAT = re.compile(
    r"^(?:.{0,40}(?:多少|是什么|什么意思|如何理解).{0,20}|.{0,30}(?:营收|收入).{0,20})$",
    re.I,
)
_COMPLEX_PAT = re.compile(r"对比|比较|两年|核实|再查|验证|口径|母公司|合并", re.I)


def _is_simple_kb_query(query: str) -> bool:
    q = (query or "").strip()
    if not q or _COMPLEX_PAT.search(q):
        return False
    return bool(_SIMPLE_PAT.search(q)) or (len(q) <= 32 and "?" not in q and "？" not in q)


def resolve_agent_route(
    *,
    user_query: str,
    agent_mode: AgentMode | str,
    allow_kb_write: bool,
    has_kb_scope: bool,
    prefetch_result: dict[str, Any] | None,
    hermes_configured: bool,
) -> AgentRoute:
    from backend.config import settings
    from backend.services.agent_kb_fast_path import prefetch_has_usable_evidence, query_implies_kb_write
    from backend.services.evidence_pack import pack_coverage_sufficient, query_needs_hermes_orchestration

    mode = (agent_mode or "standard").strip().lower()
    if mode not in ("auto", "fast", "standard", "deep"):
        mode = "standard"

    pack = (prefetch_result or {}).get("evidence_pack") if prefetch_result else None
    merged_cites = list((prefetch_result or {}).get("citations") or []) if prefetch_result else []
    sufficient = (
        pack_coverage_sufficient(pack, user_query=user_query, citations=merged_cites)
        if pack
        else prefetch_has_usable_evidence(prefetch_result)
    )
    needs_orch = query_needs_hermes_orchestration(user_query, pack) if pack else False

    if not has_kb_scope:
        # 无 KB：Hermes 已配置时一律走 Hermes（含「快速」UI 档）。
        # 注意：这不影响「已选知识库 + 快速」→ 仍 Tier 0 本地综合（见下方 mode == fast）。
        if hermes_configured:
            if mode == "deep":
                return AgentRoute.hermes_full
            return AgentRoute.hermes_lite
        if mode == "fast":
            return AgentRoute.fast
        return AgentRoute.fast
    if allow_kb_write and query_implies_kb_write(user_query):
        return AgentRoute.hermes_full
    if mode == "deep":
        # 深度：始终 Hermes 全编排；预检索仅作起点，不降级 Tier 0
        return AgentRoute.hermes_full
    # 快速模式：规制强制 Tier 0；证据不足由本地综合 + pack.gaps 提示缩 scope，不升 Hermes
    if mode == "fast":
        return AgentRoute.fast

    tier0_standard = bool(getattr(settings, "hermes_agent_standard_tier0", True))
    simple_fast = bool(getattr(settings, "hermes_agent_simple_query_fast", True))
    if not simple_fast and getattr(settings, "hermes_agent_kb_fast_path", False):
        simple_fast = True

    if mode == "standard":
        # 用户显式选「标准」= Tier 1 Hermes lite，不因 pack 覆盖率够而降级本地
        if hermes_configured and has_kb_scope:
            return AgentRoute.hermes_lite
        return AgentRoute.fast

    if mode == "auto":
        if simple_fast and _is_simple_kb_query(user_query) and sufficient:
            return AgentRoute.fast
        if tier0_standard and sufficient and not needs_orch:
            return AgentRoute.fast
        if hermes_configured:
            return AgentRoute.hermes_lite
        return AgentRoute.fast

    if hermes_configured:
        return AgentRoute.hermes_lite
    return AgentRoute.fast


def kb_ask_budget_for_route(route: AgentRoute) -> int | None:
    from backend.config import settings

    if route == AgentRoute.hermes_lite:
        return int(getattr(settings, "hermes_agent_kb_ask_budget_lite", 2) or 2)
    if route == AgentRoute.hermes_full:
        # Tier 2：不限制 orientg_kb_ask 次数（由 Hermes 多轮编排）
        cap = int(getattr(settings, "hermes_agent_kb_ask_budget_full", 0) or 0)
        return cap if cap > 0 else None
    return None


def route_to_agent_tier(route: AgentRoute | str) -> int:
    v = route.value if isinstance(route, AgentRoute) else str(route)
    if v == AgentRoute.fast.value:
        return 0
    if v == AgentRoute.hermes_lite.value:
        return 1
    return 2


def hermes_prefetch_status_message(route: AgentRoute) -> str:
    if route == AgentRoute.fast:
        return "Evidence Pack 已就绪，正在基于证据本地生成回答（Tier 0）…"
    if route == AgentRoute.hermes_lite:
        return "Evidence Pack 已就绪，Hermes 标准编排（Tier 1，补检索预算受限）…"
    if route == AgentRoute.hermes_full:
        return "Evidence Pack 已就绪，Hermes 深度编排（Tier 2）…"
    return "知识库预检索已完成…"
