"""Hermes 深度轮 orientg_kb_ask 引导：在 Runs 启动前由网关代调 MCP，并注入取证摘要。"""

from __future__ import annotations

from typing import Any


def should_prime_kb_ask_before_hermes_run(
    *,
    orientg_route: str | None,
    kb_scope: dict[str, Any] | None,
    user_query: str = "",
) -> bool:
    from backend.config import settings
    from backend.services.kb_retrieval_plan import query_wants_personnel_structure
    from backend.services.orientg_agent_presentation import kb_scope_nonempty

    route = (orientg_route or "").strip().lower()
    if not (route == "hermes_full" and kb_scope_nonempty(kb_scope)):
        return False
    # 目标 4：native 人员深度由 Hermes 自调 MCP；跳过网关 primer（避免 gateway 再 +1）
    if getattr(settings, "hermes_native_mcp_reply", False) and query_wants_personnel_structure(
        user_query
    ):
        return False
    return True


def kb_ask_tool_invocation_hint(
    *,
    session_key: str,
    user_query: str,
    native_mode: bool | None = None,
) -> dict[str, Any]:
    from backend.config import settings

    q = (user_query or "").strip()
    sk = (session_key or "").strip()
    native = settings.hermes_native_mcp_reply if native_mode is None else bool(native_mode)
    if native:
        instruction = (
            "调用 mcp_orientg_orientg_kb_ask（query 用中文、含 hermes_session_key）。"
            "返回含 agent_payload（orientg_kb_ask_v2）与证据节选。"
            "人员深度横比：**至少 2 次** MCP（首轮取证 + 一轮不同 query 核证/补缺）；"
            "若 next_action=verify_gap_then_write_final：先按 verification_queries 核实，再成稿；"
            "若 next_action=write_final_answer_now：立即用中文写终稿，必须含 "
            "`### 人员结构对照` 表（填入 evidence[].metrics 硬数字如 1378/946/242/70）+ "
            "`### 对比分析` + `### 口径说明`。"
            "禁止英文 planning、禁止总体规模/差距倍数（如 22.6 倍）、禁止核心指标对照旧模板。"
            "禁止重复完全相同的 query；禁止 terminal/curl/execute_code。"
        )
    else:
        instruction = (
            "调用 MCP 工具 mcp_orientg_orientg_kb_ask（参数 query + hermes_session_key）；"
            "禁止 terminal/shell/read_file/execute_code 模拟 KB 访问。"
            "MCP 的 reply 含「证据节选」正文（docling section / excel chunk）；收到后**直接成稿**，"
            "勿因「缺数据」反复空转检索（Hermes tool_loop_guardrails 默认仅 warn，"
            "Orient-G 网关会在多次 kb_ask 后强制收束）。"
            "深度模式：Runs 第一轮推理后须进入 tool round，1–2 次 MCP 足够。"
        )
    return {
        "name": "orientg_kb_ask",
        "hermes_tool_name": "mcp_orientg_orientg_kb_ask",
        "required_args": ["query", "hermes_session_key"],
        "forbidden_alternatives": ["terminal", "execute_code", "curl", "python -c"],
        "example": {"query": q, "hermes_session_key": sk},
        "instruction": instruction,
        "first_tool_round_required": True,
        "native_mcp_v2": native,
    }


def format_kb_ask_primer_for_instructions(
    *,
    query: str,
    reply: str,
    citations: list[dict[str, Any]] | None = None,
    native_mode: bool | None = None,
) -> str:
    """注入 bootstrap 元数据；legacy 模式不写入完整摘要；native 模式减轻矛盾指令。"""
    from backend.config import settings

    native = settings.hermes_native_mcp_reply if native_mode is None else bool(native_mode)
    cite_lines: list[str] = []
    for c in (citations or [])[:5]:
        if not isinstance(c, dict):
            continue
        doc = str(c.get("doc_id") or c.get("title") or "doc").strip()
        cite_lines.append(f"- {doc}")
    cites = "\n".join(cite_lines) if cite_lines else "- （无引用）"
    reply_len = len((reply or "").strip())
    if native:
        preview = (reply or "").strip()[:280]
        preview_block = f"\n网关线索摘要（预览）:\n{preview}\n" if preview else ""
        return (
            "## Orient-G 网关 bootstrap（Hermes 原生 MCP v2）\n"
            f"primer query: {query.strip()}\n"
            f"引用 doc:\n{cites}\n"
            f"{preview_block}"
            "成稿前 **必须** 调用 mcp_orientg_orientg_kb_ask（**首轮即调**，"
            "禁止未调工具先写终稿）；人员深度横比须 **≥2 次**（取证 + 不同 query 核证）。\n"
            "以 MCP 返回的 **agent_payload + 证据节选** 为准中文成稿。\n"
            "网关线索摘要**不得**直接作为终稿；禁止推算/推断/约N人。\n"
            "若 next_action=verify_gap_then_write_final：先核实再成稿；"
            "禁止重复完全相同的 query。\n"
            "禁止 terminal / execute_code / curl。\n"
        )
    return (
        "## Orient-G 网关 bootstrap 预检索（不可替代 Hermes MCP）\n"
        f"primer query: {query.strip()}\n"
        f"网关摘要长度: {reply_len} 字（**不得**直接作为终稿或引用依据）\n"
        f"引用 doc（须用 MCP 重新检索核实）:\n{cites}\n"
        "成稿前 **必须** 至少调用一次 mcp_orientg_orientg_kb_ask（参数 query + hermes_session_key）。\n"
        "禁止 terminal / execute_code / curl。\n"
    )


def primer_reply_belongs_in_hermes_instructions() -> bool:
    """产品约定：完整 primer 正文不得注入 Hermes instructions。"""
    return False


def build_mcp_retry_runs_body(
    *,
    user_query: str,
    session_key: str,
    model: str,
    suggested_queries: list[str] | None = None,
) -> dict[str, Any]:
    """首 run 未调 MCP 时的 MCP 优先重试请求体。"""
    q = (user_query or "").strip()
    sk = (session_key or "").strip()
    lines = [f"- {str(x).strip()}" for x in (suggested_queries or []) if str(x).strip()]
    if not lines and q:
        lines = [f"- {q}"]
    suggest = "\n".join(lines[:4]) if lines else f"- {q}"
    instructions = (
        "## Orient-G MCP 硬性要求（重试 run）\n"
        f"hermes_session_key: {sk}\n"
        "在输出分析报告之前，**必须先**调用 mcp_orientg_orientg_kb_ask 至少 1 次。\n"
        f"建议 query:\n{suggest}\n"
        "MCP reply 含证据节选正文；1–2 次检索足够，禁止反复空转。\n"
        "未调用 MCP 禁止成稿；禁止 terminal / read_file / execute_code。\n"
    )
    return {
        "model": model,
        "input": q or "请调用 orientg_kb_ask 检索知识库",
        "session_id": sk,
        "toolsets": ["orientg"],
        "instructions": instructions,
    }


def build_mcp_verify_continue_runs_body(
    *,
    user_query: str,
    session_key: str,
    model: str,
    verification_queries: list[str] | None = None,
) -> dict[str, Any]:
    """人员深横比：已取证 1 次但仍缺核证轮时的续跑（不计 hermes_mcp_retry）。"""
    q = (user_query or "").strip()
    sk = (session_key or "").strip()
    lines = [f"- {str(x).strip()}" for x in (verification_queries or []) if str(x).strip()]
    if not lines:
        lines = [
            "- YYCQ 2025 1.1信息-人员 研发 运营",
            "- 可比公司A 2025 销售人员 运营人员 员工数量",
        ]
    suggest = "\n".join(lines[:4])
    instructions = (
        "## Orient-G MCP 核证续跑（人员深度横比 · 非空转重试）\n"
        f"hermes_session_key: {sk}\n"
        "上一轮已取证，但仍须 **再调 1 次** mcp_orientg_orientg_kb_ask 做核证/补缺，"
        "query **必须与用户原横比问句不同**（选下方建议之一）。\n"
        f"建议核实 query:\n{suggest}\n"
        "核证后立即用中文写终稿：`### 人员结构对照` + `### 对比分析` + `### 口径说明`；"
        "禁止推算/推断/约N人；禁止重复完全相同的 query；禁止 terminal。\n"
    )
    return {
        "model": model,
        "input": q or "请再调 orientg_kb_ask 核实后成稿",
        "session_id": sk,
        "toolsets": ["orientg"],
        "instructions": instructions,
    }




HERMES_NATIVE_ORCHESTRATION_SOURCE = "hermes_native_orchestration"


def orchestrate_personnel_verify_kb_ask(
    *,
    user_token: str,
    verification_query: str,
    kb_scope: dict[str, Any] | None,
    attached_doc_ids: list[str] | None = None,
    fixtures: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """人员横比 E 尺：异常兜底由 Orient-G 代跑 kb_ask（计 **gateway**，不得冒充 Hermes 自调）。"""
    q = (verification_query or "").strip()
    if not q:
        return [], None

    from backend.services.kb_scope_resolve import resolve_kb_scope_for_ask
    from backend.services.knowledge_pipeline import ask_knowledge

    tenant_id = (fixtures or {}).get("tenant_id") or "tenant1"
    resolved = resolve_kb_scope_for_ask(
        tenant_id,
        kb_scope or {},
        attached_doc_ids=attached_doc_ids,
    )
    res = ask_knowledge(
        user_token,
        q,
        selected_collection_ids=list(resolved.get("collection_ids") or []) or None,
        selected_table_ids=list(resolved.get("table_ids") or []) or None,
        fixtures=fixtures,
        attached_doc_ids=list(resolved.get("attached_doc_ids") or []) or None,
        limit_to_attached=bool(resolved.get("limit_to_attached")),
    )
    status = "completed" if not res.get("denied") else "denied"
    preview = q[:72]
    events: list[dict[str, Any]] = [
        {
            "type": "tool_progress",
            "tool": "mcp_orientg_orientg_kb_ask",
            "status": "running",
            "message": f"Hermes 验证补检索 orientg_kb_ask：{preview}",
            "source": HERMES_NATIVE_ORCHESTRATION_SOURCE,
        },
        {
            "type": "tool_progress",
            "tool": "mcp_orientg_orientg_kb_ask",
            "status": status,
            "message": f"Hermes 验证补检索 orientg_kb_ask 完成：{preview}",
            "source": HERMES_NATIVE_ORCHESTRATION_SOURCE,
        },
    ]
    if res.get("denied"):
        return events, None
    return events, {
        "query": q,
        "reply": str(res.get("reply") or ""),
        "citations": list(res.get("citations") or []),
        "result": res,
    }


def run_kb_ask_primer(
    *,
    user_token: str,
    user_query: str,
    kb_scope: dict[str, Any] | None,
    attached_doc_ids: list[str] | None = None,
    fixtures: dict[str, Any] | None = None,
    enabled_skills: list[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Tier 2：Hermes Runs 启动前执行一次 orientg_kb_ask，返回 SSE 事件与 ask 结果。"""
    q = (user_query or "").strip()
    if not q:
        return [], None

    from backend.services.kb_scope_resolve import resolve_kb_scope_for_ask
    from backend.services.knowledge_pipeline import ask_knowledge

    tenant_id = (fixtures or {}).get("tenant_id") or "tenant1"
    resolved = resolve_kb_scope_for_ask(
        tenant_id,
        kb_scope or {},
        attached_doc_ids=attached_doc_ids,
    )
    res = ask_knowledge(
        user_token,
        q,
        selected_collection_ids=list(resolved.get("collection_ids") or []) or None,
        selected_table_ids=list(resolved.get("table_ids") or []) or None,
        fixtures=fixtures,
        attached_doc_ids=list(resolved.get("attached_doc_ids") or []) or None,
        limit_to_attached=bool(resolved.get("limit_to_attached")),
    )
    status = "completed" if not res.get("denied") else "denied"
    preview = q[:60]
    events: list[dict[str, Any]] = [
        {
            "type": "tool_progress",
            "tool": "orientg_kb_ask",
            "status": "running",
            "message": f"网关引导：orientg_kb_ask（{preview}）",
            "source": "orientg_gateway_primer",
        },
        {
            "type": "tool_progress",
            "tool": "orientg_kb_ask",
            "status": status,
            "message": f"网关引导：orientg_kb_ask 完成（{preview}）",
            "source": "orientg_gateway_primer",
        },
    ]
    if res.get("denied"):
        return events, None
    return events, {
        "query": q,
        "reply": str(res.get("reply") or ""),
        "citations": list(res.get("citations") or []),
        "result": res,
    }
