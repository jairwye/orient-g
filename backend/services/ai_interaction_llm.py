from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text

from backend.config import settings
from backend.database import get_db
from backend.services.openai_compatible_llm import chat_completions_ollama_shaped
from backend.services.ollama_guard import post_json_with_guard
from backend.services.upstream_guard import assert_upstream_allowed


def _ollama_base() -> str:
    base = (settings.ollama_url or "").rstrip("/")
    if not base:
        raise ValueError("Ollama 未配置，请在 .env 中设置 OLLAMA_URL")
    assert_upstream_allowed(base, service_name="Ollama")
    return base


def generate_chat_reply(
    *,
    model: str,
    messages: list[dict[str, Any]],
    skill_addon: str | None = None,
) -> str:
    """
    纯对话（不走证据、不返回 citations）。
    用于“用户未显式选择知识库范围”的场景，表现应接近普通 LLM。

    skill_addon：由 backend/data/agent_skills/*/SKILL.md 拼接的 system 片段（仅已勾选且 manifest 登记的技能）。
    """
    parts = [
        "你是一个企业内网智能助手。",
        "如果用户只是寒暄/闲聊，请自然回应并引导其提出具体问题。",
        "如果用户提出事实性问题，但缺少上下文或数据来源，请先追问需要的关键信息。",
        "除非用户明确要求，否则不要编造公司内部制度、流程、金额、日期等事实。",
        "回答要简洁、友好、可执行。",
    ]
    sa = (skill_addon or "").strip()
    if sa:
        parts.append(sa[:12000])
    system = "\n".join(parts)
    msgs: list[dict[str, Any]] = [{"role": "system", "content": system}]
    for m in messages or []:
        role = str(m.get("role") or "").strip()
        content = str(m.get("content") or "")
        if role not in {"user", "assistant", "system"}:
            continue
        if not content.strip():
            continue
        # 不信任外部传入的 system，统一由本函数注入
        if role == "system":
            continue
        msgs.append({"role": role, "content": content[:8000]})

    use_model = (model or "").strip() or (settings.llm_model or "").strip()
    if settings.llm_chat_configured:
        out = chat_completions_ollama_shaped(
            messages=msgs,
            tools=None,
            model=use_model,
            timeout_s=90.0,
            kind="ai_interaction.chat",
        )
    else:
        payload = {"model": use_model or settings.ollama_model, "messages": msgs, "stream": False}
        base = _ollama_base()
        url = f"{base}/api/chat"
        out = post_json_with_guard(url=url, payload=payload, timeout_s=90.0, kind="ai_interaction.chat")
    msg = out.get("message") or {}
    return (msg.get("content") or "").strip() or "未能生成回答。"


def _load_doc_chunk_text(tenant_id: str, doc_id: str, chunk_id: str | None, chunk_seq_no: int | None) -> str | None:
    """
    取证据明文仅用于 LLM 上下文（不直接在 API 返回中暴露整段证据）。
    - ud_*：来自 kb_user_document_chunks
    - fixtures：本函数不处理（由上层用 fixtures 文本补齐）
    """
    did = (doc_id or "").strip()
    if not did or not did.startswith("ud_"):
        return None
    if chunk_id:
        with get_db() as db:
            row = db.execute(
                text(
                    """
                    SELECT chunk_text
                    FROM kb_user_document_chunks
                    WHERE doc_id=:d AND chunk_id=:c
                    """
                ),
                {"d": did, "c": str(chunk_id)},
            ).fetchone()
        return str(row[0]) if row and row[0] else None
    if chunk_seq_no is not None:
        with get_db() as db:
            row = db.execute(
                text(
                    """
                    SELECT chunk_text
                    FROM kb_user_document_chunks
                    WHERE doc_id=:d AND chunk_seq_no=:n
                    ORDER BY chunk_seq_no
                    LIMIT 1
                    """
                ),
                {"d": did, "n": int(chunk_seq_no)},
            ).fetchone()
        return str(row[0]) if row and row[0] else None
    return None


def _load_table_row_json(tenant_id: str, table_id: str, row_key: str | None) -> dict[str, Any] | None:
    tid = (tenant_id or "").strip() or "tenant1"
    tb = (table_id or "").strip()
    rk = (row_key or "").strip()
    if not tb or not rk:
        return None
    with get_db() as db:
        row = db.execute(
            text(
                """
                SELECT row_json
                FROM kb_table_rows
                WHERE tenant_id=:t AND table_id=:tb AND row_key=:rk
                ORDER BY id DESC
                LIMIT 1
                """
            ),
            {"t": tid, "tb": tb, "rk": rk},
        ).fetchone()
    if not row or not row[0]:
        return None
    try:
        obj = json.loads(str(row[0]))
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def generate_answer_with_evidence(
    *,
    tenant_id: str,
    model: str,
    user_query: str,
    citations: list[dict[str, Any]],
    fixtures: dict[str, Any],
    skill_addon: str | None = None,
) -> str:
    """
    用“证据片段 + 强约束提示词”生成答案。
    约束：只能根据证据回答；不确定就说不知道，并指出缺少什么证据。

    skill_addon：已启用技能的 SKILL.md 拼接段；不得放宽「仅依据证据」要求，仅作口径与输出形态补充。
    """
    q = (user_query or "").strip()[:800]
    if not q:
        return "问题为空。"

    evidence_blocks: list[str] = []
    for c in citations[:10]:
        et = str(c.get("evidence_type") or "")
        if et == "doc_chunk":
            doc_id = str(c.get("doc_id") or "")
            chunk_id = c.get("chunk_id")
            chunk_seq_no = c.get("chunk_seq_no")
            # fixtures 文本
            if doc_id and not doc_id.startswith("ud_"):
                for d in fixtures.get("documents") or []:
                    if str(d.get("doc_id") or "") != doc_id:
                        continue
                    for s in d.get("sections") or []:
                        for ch in s.get("chunks") or []:
                            if c.get("chunk_id") and ch.get("chunk_id") == c.get("chunk_id"):
                                txt = str(ch.get("text") or "")
                                if txt:
                                    evidence_blocks.append(f"[doc_chunk {doc_id}#{ch.get('chunk_id')}] {txt}")
                                    break
            # uploaded 文本
            txt2 = _load_doc_chunk_text(tenant_id, doc_id, str(chunk_id) if chunk_id else None, int(chunk_seq_no) if chunk_seq_no is not None else None)
            if txt2:
                evidence_blocks.append(f"[doc_chunk {doc_id}#{chunk_id or chunk_seq_no}] {txt2[:1200]}")

        if et == "table_row":
            table_id = str(c.get("table_id") or "")
            row_key = c.get("row_key")
            row = _load_table_row_json(tenant_id, table_id, str(row_key) if row_key else None)
            if row:
                evidence_blocks.append(f"[table_row {table_id}#{row_key}] {json.dumps(row, ensure_ascii=False)}")

    parts = [
        "你是财务知识库问答助手。",
        "你必须严格只根据给定的证据回答；禁止编造任何未出现在证据中的数值或条款。",
        "如果证据不足以得出结论，请明确说明“不确定/缺少证据”，并指出需要什么证据。",
        "回答要简洁、可执行；如涉及金额/日期/条款，优先引用证据中的原始字段或原句。",
    ]
    sa = (skill_addon or "").strip()
    if sa:
        parts.append(
            "以下为本次对话已启用的技能文档（补充约束）。若与上文「仅依据证据」冲突，仍以证据为准，不得用技能文档编造证据中不存在的事实。"
        )
        parts.append(sa[:12000])
    system = "\n".join(parts)
    evidence_text = "\n".join(evidence_blocks) if evidence_blocks else "(无证据片段)"
    user = f"问题：{q}\n\n证据：\n{evidence_text}\n\n请给出答案。"

    ev_msgs: list[dict[str, Any]] = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    use_model = (model or "").strip() or (settings.llm_model or "").strip()
    if settings.llm_chat_configured:
        out = chat_completions_ollama_shaped(
            messages=ev_msgs,
            tools=None,
            model=use_model,
            timeout_s=90.0,
            kind="ai_interaction.evidence_chat",
        )
    else:
        payload = {
            "model": use_model or settings.ollama_model,
            "messages": ev_msgs,
            "stream": False,
        }
        base = _ollama_base()
        url = f"{base}/api/chat"
        out = post_json_with_guard(url=url, payload=payload, timeout_s=90.0, kind="ai_interaction.evidence_chat")
    msg = out.get("message") or {}
    return (msg.get("content") or "").strip() or "未能生成回答。"

