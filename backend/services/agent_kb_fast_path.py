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


def comparison_answer_addon(user_query: str) -> str:
    q = (user_query or "").strip()
    if not q:
        return ""
    if re.search(r"对比|比较|两年|损益|营收|利润", q):
        return (
            "若用户要求对比分析表：\n"
            "1) 默认使用「合并利润表」口径；若证据仅为母公司表，须在表前用一句话标明口径。\n"
            "2) 表格前空一行，使用标准 Markdown 表格（表头行 + |---|---| 分隔行），列：项目、2025年、2024年、差额或同比。\n"
            "3) 表后单独一段「说明」与「引用证据」（doc_id 列表），不要把说明插在表格行中间。\n"
            "4) 数值必须来自证据；缺项写「缺少证据」。"
        )
    return ""


def chunk_text_for_stream(text: str, *, size: int = 96) -> list[str]:
    s = text or ""
    if not s:
        return []
    return [s[i : i + size] for i in range(0, len(s), size)]


def fast_path_status_message() -> str:
    return "Evidence Pack 已就绪，正在基于证据生成回答（Tier 0）…"


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
) -> Iterator[dict[str, Any]]:
    from backend.services.agent_kb_prefetch import synthesize_kb_reply
    from backend.services.agent_kb_router import AgentRoute, hermes_prefetch_status_message, route_to_agent_tier
    from backend.services.agent_run_registry import is_cancelled
    from backend.services.evidence_pack import pack_summary_for_sse

    pack = (prefetch_result or {}).get("evidence_pack")
    yield {
        "type": "status",
        "message": hermes_prefetch_status_message(AgentRoute.fast),
        "step": "prefetch_done",
        "agent_route": AgentRoute.fast.value,
        "agent_tier": route_to_agent_tier(AgentRoute.fast),
        "evidence_pack": pack_summary_for_sse(pack if isinstance(pack, dict) else None),
    }
    yield {
        "type": "status",
        "message": fast_path_status_message(),
        "step": "kb_fast_path",
    }
    yield {
        "type": "status",
        "message": "快速路径：Orient-G 本地 LLM 综合中（未调用 Hermes Gateway）…",
        "step": "local_llm_synth",
    }
    if is_cancelled(run_id):
        yield {"type": "error", "message": "已停止", "code": "cancelled"}
        return
    addon = comparison_answer_addon(user_query)
    skill_extra = addon
    if addon and enabled_skills is not None:
        enabled_skills = list(enabled_skills)
    synth = synthesize_kb_reply(
        tenant_id=tenant_id,
        user_query=user_query,
        prefetch_result=prefetch_result,
        fixtures=fixtures,
        enabled_skills=enabled_skills,
        model=model,
        skill_addon_extra=skill_extra or None,
        run_id=run_id,
    )
    reply = (synth.get("reply") or "").strip() or "（未能生成回答）"
    yield {
        "type": "status",
        "message": "本地 LLM 综合完成，正在输出正文…",
        "step": "local_llm_done",
    }
    for piece in chunk_text_for_stream(reply):
        yield {"type": "delta", "content": piece}
    pack = (prefetch_result or {}).get("evidence_pack")
    from backend.services.evidence_pack import pack_summary_for_sse

    yield {
        "type": "done",
        "ok": True,
        "reply": reply,
        "tenant_id": tenant_id,
        "citations": synth.get("citations") or [],
        "tool_calls": prefetch_tool_calls,
        "kb_prefetch": True,
        "kb_fast_path": True,
        "agent_route": "fast",
        "agent_tier": 0,
        "evidence_pack": pack_summary_for_sse(pack),
        "hermes_used": False,
        "synthesis": synth.get("synthesis"),
        "llm_model": synth.get("llm_model"),
        "hermes_session_id": hermes_session_id,
    }
