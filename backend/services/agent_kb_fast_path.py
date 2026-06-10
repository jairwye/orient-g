"""KB 预检索成功后的快速路径：本地证据综合 + 流式输出，避免 Hermes 重复 MCP。"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from typing import Any

from backend.config import settings

_WRITE_HINTS = ("上传", "写入", "导入", "指派", "分配", "upload", "import", "assign")


def query_implies_kb_write(query: str) -> bool:
    q = (query or "").strip().lower()
    if not q:
        return False
    return any(h in q for h in _WRITE_HINTS)


def prefetch_has_usable_evidence(prefetch_result: dict[str, Any] | None) -> bool:
    if not prefetch_result or not prefetch_result.get("ok"):
        return False
    if prefetch_result.get("denied"):
        return False
    cites = prefetch_result.get("citations") or []
    return bool(cites)


def should_use_kb_fast_path(
    prefetch_result: dict[str, Any] | None,
    *,
    user_query: str,
    allow_kb_write: bool,
) -> bool:
    """
    有 KB 范围且预检索已有 citations 时，走本地 LLM 综合（与 AI 互动一致），
    不再进入 Hermes MCP 多轮工具环（常见耗时数分钟）。
    """
    if not settings.hermes_agent_kb_fast_path:
        return False
    if not settings.hermes_agent_kb_prefetch:
        return False
    if not prefetch_has_usable_evidence(prefetch_result):
        return False
    if allow_kb_write and query_implies_kb_write(user_query):
        return False
    return True


def prefetch_system_lead(*, via_hermes: bool, evidence_pack: dict | None = None) -> str:
    gaps = (evidence_pack or {}).get("gaps") or []
    gap_hint = ""
    if gaps:
        gap_hint = "【缺项】" + "；".join(str(g) for g in gaps[:5]) + "。\n"
    if via_hermes:
        return (
            "Orient-G 网关已完成多 query 预检索并生成 Evidence Pack（见 JSON）。"
            "请优先基于 pack.facets 与 citations 作答；仅针对 gaps 中缺项可再调用 orientg_kb_ask，"
            "且 query 须与已用子 query 不同、更具体（如「合并利润表 销售费用 附注 2025」）。"
            "勿使用 terminal 编造未入库文件。\n"
            + gap_hint
        )
    return (
        "Orient-G 网关已执行预检索并生成 Evidence Pack。请用自然语言回答用户，并引用 doc_id。\n"
        + gap_hint
    )


def comparison_answer_addon(user_query: str, *, tier: str = "local") -> str:
    """对比/明细类作答规制：local=快速(Tier0)，lite=标准(Tier1)，full=深度(Tier2)。"""
    q = (user_query or "").strip()
    if not q:
        return ""
    if not re.search(r"对比|比较|两年|损益|营收|利润|明细|费用", q):
        return ""
    t = (tier or "local").strip().lower()
    if t == "full":
        return _comparison_addon_full(q)
    if t == "lite":
        return _comparison_addon_lite(q)
    return _comparison_addon_local(q)


def fast_path_answer_addon(user_query: str) -> str:
    """Tier 0 快速：严证据 + 短表结构（原标准约束下沉）。"""
    from backend.services.agent_kb_supplemental import evidence_constraint_addon

    parts = [evidence_constraint_addon(tier="local"), comparison_answer_addon(user_query, tier="local")]
    return "\n\n".join(x for x in parts if x)


def _comparison_addon_local(q: str) -> str:
    from backend.services.kb_retrieval_plan import query_wants_change_reasons

    wants_reason = query_wants_change_reasons(q)
    base = (
        "【快速·对比表】\n"
        "1) 先写一行「结论：…」（缺明细时明确写缺项，禁止编造分项金额）。\n"
        "2) 默认合并利润表口径；仅母公司证据时须标明「母公司利润表口径」。\n"
        "3) 表格前空一行，使用标准 Markdown 表（表头 + |---|---| 分隔行），"
        "列：项目、2025年、2024年、差额或同比；表后空一行再写「说明」编号列表。\n"
        "4) 数值必须来自证据原文：优先保留**元**单位与千分位；禁止四舍五入改数或「约 xxx 万」。"
        "分项无片段则写「缺少证据」。"
    )
    if wants_reason:
        base += (
            "\n5) 「说明」须含「变动原因」：仅可引用证据原文（如「主要系…」）；"
            "无原因文字时写「证据未提供变动原因说明」。"
            "禁止无 doc_id 的业务推断。"
        )
    base += (
        "\n6) 若证据含营业收入与销售费用合计，须增加「销售费用率」一行。"
        "\n7) 禁止复述 Evidence Pack；默认合并口径直接输出。"
    )
    return base


def _comparison_addon_lite(q: str) -> str:
    """标准 Tier 1：原深度合规 5 段结构 + 立即成稿约束。"""
    from backend.services.kb_retrieval_plan import query_wants_change_reasons

    wants_reason = query_wants_change_reasons(q)
    base = (
        "【标准·合规对比报告】\n"
        "1) 终稿以 `#` 标题或「结论：」开头；禁止复述 Evidence Pack 或要求用户确认口径。\n"
        "2) Evidence Pack 无缺项且 facets 已含分项金额时须**立即成稿**（禁止先写缺口说明）。\n"
        "3) 建议结构：①结论；②核心指标表（销售费用、营业收入、销售费用率）；"
        "③附注分项明细表；④变动原因（引用年报原文）；⑤口径说明。\n"
        "4) 数值须来自 citations/MCP 原文（元+千分位）；禁止「估算」「约 xxx 万」「推断」。"
        "分项缺失写「缺少证据」，不得编造。"
    )
    if wants_reason:
        base += (
            "\n5) 变动原因仅可归纳证据原文（如「主要系人员减少…」）；"
            "无原因文字时写「证据未提供变动原因说明，仅列示金额与分项对比」。"
            "禁止正文 inline doc_id / [doc_chunk] / ud_*（引用见 citations 面板）。"
        )
    base += "\n6) 禁止 orientg_kb_import_artifact；正文直接输出 Markdown 报告。"
    return base


def _comparison_addon_full(q: str) -> str:
    """深度 Tier 2：分析师级 A~E 结构 + 有引用可解读。"""
    return (
        "【深度·分析师报告】\n"
        "1) 你是唯一作者：终稿须一次性写全（禁止依赖 Orient-G 事后追加）。\n"
        "2) 成稿前若缺经营叙事/产品背景，须 1–2 次 orientg_kb_ask 补检索"
        "（如「经营情况讨论 主营业务」「市场及推广费用 变动原因」），再写终稿。\n"
        "3) 建议完整结构：①结论；②核心指标表；③分项明细表；④分项驱动分析"
        "（逐项解释变动，可联系产品/推广/人员策略，**每段须标注 doc_id**）；"
        "⑤变动原因（年报原文）；⑥盈利能力/费比影响；⑦风险提示（仅基于证据）；"
        "⑧总结与后续关注；⑨口径说明。\n"
        "4) 金额须来自证据；**允许**在 citations 支撑下写解读性段落（须标注 doc_id）；"
        "无证据的业务故事不得写。\n"
        "5) 禁止 terminal/自编脚本；禁止 orientg_kb_import_artifact。"
    )


def chunk_text_for_stream(text: str, *, size: int = 96) -> list[str]:
    s = text or ""
    if not s:
        return []
    return [s[i : i + size] for i in range(0, len(s), size)]


def fast_path_status_message() -> str:
    return "Evidence Pack 已就绪，正在基于证据生成回答（Tier 0）…"


def finalize_fast_path_reply(reply: str, *, user_query: str) -> str:
    from backend.services.hermes_stream_sanitize import finalize_agent_reply

    return finalize_agent_reply(reply, user_query=user_query, tier2_native=False)


def stream_kb_fast_path_events(
    *,
    tenant_id: str,
    user_query: str,
    prefetch_result: dict[str, Any],
    prefetch_tool_calls: list[dict[str, Any]],
    fixtures: dict[str, Any],
    enabled_skills: list[str] | None = None,
    model: str | None = None,
    hermes_session_id: str | None = None,
    run_id: str | None = None,
    user_token: str | None = None,
    kb_scope: dict[str, list[str]] | None = None,
    attached_doc_ids: list[str] | None = None,
) -> Iterator[dict[str, Any]]:
    from backend.services.agent_kb_prefetch import synthesize_kb_reply
    from backend.services.agent_kb_router import AgentRoute, route_to_agent_tier
    from backend.services.agent_kb_supplemental import (
        needs_fast_path_narrative_supplemental,
        run_supplemental_kb_asks,
    )
    from backend.services.agent_run_registry import is_cancelled
    from backend.services.evidence_pack import pack_summary_for_sse

    working_prefetch = dict(prefetch_result or {})
    tool_calls = list(prefetch_tool_calls or [])
    pack = working_prefetch.get("evidence_pack")
    yield {
        "type": "status",
        "message": fast_path_status_message(),
        "step": "prefetch_done",
        "agent_route": AgentRoute.fast.value,
        "agent_tier": route_to_agent_tier(AgentRoute.fast),
        "evidence_pack": pack_summary_for_sse(pack if isinstance(pack, dict) else None),
    }
    if (
        user_token
        and kb_scope is not None
        and needs_fast_path_narrative_supplemental(
            prefetch_result=working_prefetch,
            user_query=user_query,
            enabled_skills=enabled_skills,
        )
    ):
        yield {
            "type": "status",
            "message": "快速路径：检测到变动说明缺项，正在补检索 narrative 证据…",
            "step": "fast_supplemental_kb",
        }
        merged, sup_tools = run_supplemental_kb_asks(
            user_token=user_token,
            user_query=user_query,
            prefetch_result=working_prefetch,
            kb_scope=kb_scope,
            attached_doc_ids=attached_doc_ids,
            fixtures=fixtures,
            max_queries=3,
            prefetch_tier="local",
            enabled_skills=enabled_skills,
        )
        if merged:
            working_prefetch = merged
            tool_calls.extend(sup_tools)
            for tc in sup_tools:
                q = str(tc.get("query") or "")[:60]
                yield {
                    "type": "tool_call",
                    "name": "orientg_kb_ask",
                    "status": tc.get("status") or "ok",
                    "message": f"补检索：{q}" if q else "补检索：orientg_kb_ask",
                }
            pack = working_prefetch.get("evidence_pack")
            yield {
                "type": "status",
                "message": "narrative 补检索完成，继续本地综合…",
                "step": "fast_supplemental_done",
                "evidence_pack": pack_summary_for_sse(pack if isinstance(pack, dict) else None),
            }
    yield {
        "type": "status",
        "message": "快速路径：Orient-G 本地 LLM 综合中（未调用 Hermes Gateway）…",
        "step": "local_llm_synth",
    }
    if is_cancelled(run_id):
        yield {"type": "error", "message": "已停止", "code": "cancelled"}
        return
    addon = fast_path_answer_addon(user_query)
    skill_extra = addon
    if addon and enabled_skills is not None:
        enabled_skills = list(enabled_skills)
    synth = synthesize_kb_reply(
        tenant_id=tenant_id,
        user_query=user_query,
        prefetch_result=working_prefetch,
        fixtures=fixtures,
        enabled_skills=enabled_skills,
        model=model,
        skill_addon_extra=skill_extra or None,
        run_id=run_id,
    )
    reply = finalize_fast_path_reply(
        (synth.get("reply") or "").strip() or "（未能生成回答）",
        user_query=user_query,
    )
    yield {
        "type": "status",
        "message": "本地 LLM 综合完成，正在输出正文…",
        "step": "local_llm_done",
    }
    for piece in chunk_text_for_stream(reply):
        yield {"type": "delta", "content": piece}
    pack = (working_prefetch or {}).get("evidence_pack")
    from backend.services.evidence_pack import pack_summary_for_sse

    yield {
        "type": "done",
        "ok": True,
        "reply": reply,
        "tenant_id": tenant_id,
        "citations": synth.get("citations") or [],
        "tool_calls": tool_calls,
        "kb_prefetch": True,
        "kb_fast_path": True,
        "kb_supplemental": bool(working_prefetch.get("kb_supplemental")),
        "agent_route": "fast",
        "agent_tier": 0,
        "evidence_pack": pack_summary_for_sse(pack),
        "hermes_used": False,
        "synthesis": synth.get("synthesis"),
        "llm_model": synth.get("llm_model"),
        "hermes_session_id": hermes_session_id,
    }
