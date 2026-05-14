"""
AI 互动（v1.2.2）：chat + skills/tools allow-list（最小闭环）。

当前实现目标：
- 支持前端提交多轮 messages
- 支持 kb_scope（collections/tables/folders）→ 映射到 knowledge_pipeline.ask_knowledge
- 保留现有 ACL pre-filter、限流/降级、审计链路（复用 knowledge 路由同口径）
"""

from __future__ import annotations

from typing import Any, Literal

import jwt
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from backend.config import settings
from backend.services.knowledge_pipeline import ask_knowledge
from backend.services.knowledge_acl import load_fixtures
from backend.services.task_queue import get_stats as get_queue_stats
from backend.services.online_rate_limiter import allow as rate_limit_allow


router = APIRouter()
ALGORITHM = "HS256"


def _get_token_from_request(request: Request) -> str | None:
    auth = request.headers.get("Authorization") or ""
    if auth.startswith("Bearer "):
        t = auth[7:].strip()
        if t:
            return t
    return request.headers.get("X-Auth-Token") or None


def _get_username_from_request(request: Request) -> str | None:
    token = _get_token_from_request(request)
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.auth_secret, algorithms=[ALGORITHM])
        return (payload.get("sub") or "").strip() or None
    except Exception:
        return None


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class KbScope(BaseModel):
    selected_collection_ids: list[str] | None = None
    selected_table_ids: list[str] | None = None
    selected_folder_ids: list[str] | None = None


class ChatBody(BaseModel):
    messages: list[ChatMessage]
    kb_scope: KbScope | None = None
    enabled_skills: list[str] | None = None
    enabled_tools: list[str] | None = None
    model: str | None = None


@router.post("/chat")
def ai_interaction_chat(request: Request, body: ChatBody):
    token = _get_token_from_request(request)
    if not token:
        raise HTTPException(status_code=401, detail="not authenticated")

    fixtures = load_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    uname = _get_username_from_request(request)

    # 2.e：队列堆积降级（与 /knowledge/ask 同口径）
    try:
        qs = get_queue_stats()
        if int(qs.get("queue_size_high") or 0) >= int(settings.queue_degrade_high_threshold):
            raise HTTPException(status_code=503, detail="系统繁忙（队列堆积），请稍后重试")
    except HTTPException:
        raise
    except Exception:
        pass

    # 2.e：在线互动按用户限速（与 /knowledge/ask 同口径）
    key = f"ai-interaction.chat:{tenant_id}:{uname or 'anonymous'}"
    if not rate_limit_allow(key=key):
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")

    # 取最后一条 user 消息作为 query（v1.2.2 最小闭环；后续可做多轮总结/压缩）
    query = ""
    for m in reversed(body.messages or []):
        if m.role == "user":
            query = (m.content or "").strip()
            break
    if not query:
        raise HTTPException(status_code=400, detail="empty user message")

    scope = body.kb_scope or KbScope()
    raw_selected_collection_ids = [str(x).strip() for x in (scope.selected_collection_ids or []) if str(x).strip()]
    raw_selected_table_ids = [str(x).strip() for x in (scope.selected_table_ids or []) if str(x).strip()]
    raw_selected_folder_ids = [str(x).strip() for x in (scope.selected_folder_ids or []) if str(x).strip()]

    # 方案 B：只有“用户显式选择了范围”才走知识库检索；否则走纯对话（普通 LLM）
    explicit_scope_selected = bool(raw_selected_collection_ids or raw_selected_table_ids or raw_selected_folder_ids)

    selected_collection_ids = list(raw_selected_collection_ids)
    selected_table_ids = list(raw_selected_table_ids)

    # folder_ids → collection_ids（可见性最终仍由 ACL/子集校验保证）
    folder_ids = list(raw_selected_folder_ids)
    if folder_ids:
        try:
            from backend.services.kb_folders import list_folders

            folders = list_folders(tenant_id)
            f2c = {str(f.get("folder_id")): list(f.get("collection_ids") or []) for f in folders}
            for fid in folder_ids:
                for cid in f2c.get(fid, []) or []:
                    cc = str(cid).strip()
                    if cc:
                        selected_collection_ids.append(cc)
        except Exception:
            # folder 解析失败不阻断主流程（仍可按用户显式选中的 collections 继续）
            pass

    # 去重
    seen = set()
    selected_collection_ids = [x for x in selected_collection_ids if not (x in seen or seen.add(x))]
    seen2 = set()
    selected_table_ids = [x for x in selected_table_ids if not (x in seen2 or seen2.add(x))]

    # v1.2.2：skills/tools allow-list 先仅回传，暂不执行（执行逻辑在后续 b/c/d 中落地）
    tool_calls: list[dict[str, Any]] = []
    enabled_tools = [str(x).strip() for x in (body.enabled_tools or []) if str(x).strip()]
    enabled_skills = [str(x).strip() for x in (body.enabled_skills or []) if str(x).strip()]
    if enabled_tools:
        tool_calls.append({"id": "enabled_tools", "kind": "meta", "names": enabled_tools})
    if enabled_skills:
        tool_calls.append({"id": "enabled_skills", "kind": "meta", "names": enabled_skills})

    # --- Tool：Docling convert（v1.2.2.c 最小触发）---
    # 触发方式：用户在消息中包含 doc_id（ud_...）并提到 docling/解析
    if "tool.docling.convert" in enabled_tools and ("docling" in query.lower() or "解析" in query):
        import re
        from pathlib import Path

        from backend.services.kb_documents import _doc_root  # type: ignore

        m = re.search(r"(ud_[0-9a-fA-F]+)", query)
        if m:
            doc_id = m.group(1)
            try:
                from backend.services import kb_documents as kb_docs
                archive_md = _doc_root(tenant_id, doc_id) / "archive" / "full.md"
                owner = kb_docs.get_document_owner(tenant_id, doc_id)
                if owner != uname:
                    raise PermissionError("forbidden")
                if not archive_md.exists():
                    raise FileNotFoundError("archive/full.md not found")
                head = archive_md.read_text(encoding="utf-8", errors="replace")[:2000]
                tool_calls.append({"id": "tool_call_1", "kind": "tool", "name": "tool.docling.convert", "ok": True, "doc_id": doc_id})
                return {
                    "denied": False,
                    "reply": f"已读取 Docling 解析产物（{doc_id}）头部片段：\n\n{head}",
                    "citations": [{"evidence_type": "doc_chunk", "doc_id": doc_id, "chunk_id": None, "chunk_seq_no": None}],
                    "tool_calls": tool_calls,
                }
            except Exception as e:
                tool_calls.append({"id": "tool_call_1", "kind": "tool", "name": "tool.docling.convert", "ok": False, "error": str(e)})
                return {"denied": False, "reply": f"Docling 工具执行失败：{e}", "citations": [], "tool_calls": tool_calls}

    # --- Skills：基础数据生成项目核算表（v1.2.2.b，最小触发）---
    if "skill.project_accounting_table.v1" in enabled_skills and ("项目核算表" in query or "生成核算表" in query):
        try:
            from backend.services.skills.project_accounting_table import run as run_skill

            # 轻量提取 project_key/period：从 query 中抓取 “项目X”“YYYY-MM”
            project_key = "项目A"
            period = None
            for token in query.replace("：", ":").split():
                if token.startswith("proj"):
                    project_key = token
                if len(token) == 7 and token[4] == "-" and token[:4].isdigit() and token[5:].isdigit():
                    period = token
            skill_res = run_skill(tenant_id, uname or "anonymous", project_key=project_key, period=period, fixtures=fixtures)
            tool_calls.append({"id": "skill_call_1", "kind": "skill", "name": "skill.project_accounting_table.v1", "ok": True})
            return {
                "denied": False,
                "reply": skill_res.get("summary") or "已生成项目核算表。",
                "citations": skill_res.get("citations") or [],
                "tool_calls": tool_calls,
            }
        except Exception as e:
            tool_calls.append({"id": "skill_call_1", "kind": "skill", "name": "skill.project_accounting_table.v1", "ok": False, "error": str(e)})
            return {
                "denied": False,
                "reply": f"技能执行失败：{e}",
                "citations": [],
                "tool_calls": tool_calls,
            }

    # --- 纯对话：未显式选择 KB 范围时，不做 RAG 检索 ---
    model = (body.model or "").strip() or (
        (settings.llm_model or "").strip() if settings.llm_chat_configured else (settings.ollama_model or "").strip()
    ) or settings.ollama_model
    if not explicit_scope_selected:
        if not settings.chat_llm_available:
            return {
                "denied": False,
                "reply": "当前未选择知识库范围；且未配置对话 LLM（请设置 LLM_BASE_URL+LLM_MODEL 或 OLLAMA_URL）。",
                "citations": [],
                "tool_calls": tool_calls,
            }
        try:
            from backend.services.agent_skills_loader import build_system_addon_for_enabled_skills
            from backend.services.ai_interaction_llm import generate_chat_reply

            skill_addon = build_system_addon_for_enabled_skills(enabled_skills)
            llm_reply = generate_chat_reply(
                model=model,
                messages=[m.model_dump() for m in (body.messages or [])],  # type: ignore[attr-defined]
                skill_addon=skill_addon or None,
            )
            return {"denied": False, "reply": llm_reply, "citations": [], "tool_calls": tool_calls, "llm_model": model}
        except Exception as e:
            return {
                "denied": False,
                "reply": f"纯对话生成失败：{e}",
                "citations": [],
                "tool_calls": tool_calls,
                "llm_model": model,
            }

    res = ask_knowledge(
        token,
        query,
        selected_collection_ids=selected_collection_ids if selected_collection_ids else None,
        selected_table_ids=selected_table_ids if selected_table_ids else None,
        fixtures=fixtures,
    )
    if res.get("denied"):
        raise HTTPException(status_code=403, detail=res.get("deny_reason") or "denied")

    # --- LLM：基于证据生成最终答复（v1.2.2：AI互动需要调用 LLM） ---
    # 说明：ask_knowledge 的 reply 仅用于检索可观测；最终面向用户的回答由 LLM 在证据约束下生成。
    if not settings.chat_llm_available:
        res["tool_calls"] = tool_calls
        res["reply"] = (res.get("reply") or "") + "（未配置对话 LLM，当前仅返回检索结果摘要）"
        return res
    try:
        from backend.services.agent_skills_loader import build_system_addon_for_enabled_skills
        from backend.services.ai_interaction_llm import generate_answer_with_evidence

        skill_addon_kb = build_system_addon_for_enabled_skills(enabled_skills)
        llm_reply = generate_answer_with_evidence(
            tenant_id=tenant_id,
            model=model,
            user_query=query,
            citations=list(res.get("citations") or []),
            fixtures=fixtures,
            skill_addon=skill_addon_kb or None,
        )
        res["reply"] = llm_reply
        res["llm_model"] = model
    except Exception as e:
        # 回退：至少把检索摘要返回，避免全失败
        res["reply"] = (res.get("reply") or "") + f"（LLM 生成失败：{e}）"

    res["tool_calls"] = tool_calls
    return res


@router.get("/skills")
def ai_interaction_skills_catalog(request: Request):
    """
    返回 manifest 登记的 Agent Skill：含 SKILL.md 全文，供 AI 互动页「技能」Tab 展示。
    与运行时注入一致（build_system_addon_for_enabled_skills 使用相同加载器）。
    """
    if not _get_token_from_request(request):
        raise HTTPException(status_code=401, detail="not authenticated")
    from backend.services.agent_skills_loader import list_skill_documents

    return {"skills": list_skill_documents()}


@router.get("/models")
def ai_interaction_models(request: Request):
    if not _get_token_from_request(request):
        raise HTTPException(status_code=401, detail="not authenticated")
    items: list[dict[str, Any]] = []
    default_id = settings.ollama_model
    if settings.llm_chat_configured:
        mid = (settings.llm_model or "").strip()
        if mid:
            items = [{"id": mid, "label": mid}]
        default_id = mid or default_id
    elif settings.ollama_configured:
        try:
            from backend.services.ollama_tags import list_models

            items = list_models()
        except Exception:
            items = []
    if not items:
        default_id = (
            (settings.llm_model or "").strip()
            if settings.llm_chat_configured
            else (settings.ollama_model or "").strip()
        ) or "model"
        items = [{"id": default_id, "label": default_id}]
    return {"items": items, "default": default_id}

