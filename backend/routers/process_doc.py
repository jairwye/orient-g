"""
自然语言 → 标准财务业务流程文档：录入、生成、站内预览与下载。
"""
import logging

import jwt
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, field_validator

from backend.config import settings
from backend.services.process_doc import generate_process_doc, load_rules, save_rules, suggest_prompt_from_natural_language
from backend.services.feishu_sync import sync_doc_to_feishu
from backend.services.user_acl_store import get_user

logger = logging.getLogger(__name__)

router = APIRouter()
ALGORITHM = "HS256"


class GenerateBody(BaseModel):
    natural_language: str
    process_type_id: str | None = None


class SyncFeishuBody(BaseModel):
    title: str
    markdown: str


class ProcessTypeRule(BaseModel):
    id: str
    name: str | None = None
    description: str | None = None
    output_schema: dict | None = None
    prompt_instruction: str = ""
    natural_language_rule: str | None = None


class SuggestFromNaturalLanguageBody(BaseModel):
    natural_language: str
    process_type_id: str | None = None


class RulesBody(BaseModel):
    schema_version: str | None = None
    process_types: list[ProcessTypeRule]

    @field_validator("process_types")
    @classmethod
    def process_types_nonempty_with_instruction(cls, v: list[ProcessTypeRule]) -> list[ProcessTypeRule]:
        if not v:
            raise ValueError("process_types 不能为空")
        for t in v:
            if not (t.id and (t.prompt_instruction or "").strip()):
                raise ValueError("每个流程类型必须包含 id 与 prompt_instruction")
        return v


def _get_username_from_request(request: Request) -> str | None:
    auth = request.headers.get("Authorization") or ""
    token = ""
    if auth.startswith("Bearer "):
        token = auth[7:].strip()
    token = token or (request.headers.get("X-Auth-Token") or "").strip()
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.auth_secret, algorithms=[ALGORITHM])
        return (payload.get("sub") or "").strip() or None
    except Exception:
        return None


def _require_admin(request: Request) -> str:
    un = _get_username_from_request(request)
    if not un:
        raise HTTPException(status_code=401, detail="not authenticated")
    u = get_user(un) or {}
    roles = [str(x).strip().lower() for x in (u.get("roles") or [])]
    if "admin" not in roles and "管理层" not in roles:
        raise HTTPException(status_code=403, detail="forbidden")
    return un


@router.get("/rules")
def get_rules(request: Request):
    """返回完整流程规则（供前端展示与编辑）。"""
    _require_admin(request)
    return load_rules()


@router.post("/rules/suggest-from-natural-language")
def suggest_from_natural_language(body: SuggestFromNaturalLanguageBody, request: Request):
    """根据用户自然语言描述，用 LLM 生成建议的 prompt_instruction 与可选的 output_schema。"""
    _require_admin(request)
    if not settings.chat_llm_available:
        raise HTTPException(
            status_code=503,
            detail="LLM 未配置：请在 .env 设置 LLM_BASE_URL + LLM_MODEL（OpenAI 兼容），或设置 OLLAMA_URL 使用 Ollama。",
        )
    text = (body.natural_language or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="请填写自然语言描述")
    try:
        result = suggest_prompt_from_natural_language(text)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("根据自然语言生成规则建议失败")
        raise HTTPException(status_code=500, detail="生成建议失败，请检查 LLM 或 Ollama 服务")


@router.put("/rules")
def put_rules(body: RulesBody, request: Request):
    """保存流程规则，校验后写回 process_rules.json。"""
    _require_admin(request)
    payload = {
        "schema_version": body.schema_version or "1",
        "process_types": [t.model_dump(exclude_none=False) for t in body.process_types],
    }
    try:
        save_rules(payload)
        return {"ok": True}
    except OSError as e:
        logger.exception("写入规则文件失败")
        raise HTTPException(status_code=500, detail="保存规则失败，请检查文件权限")


@router.get("/schema")
def get_schema(request: Request):
    """返回当前可用的流程类型与输出结构说明（供前端展示）。"""
    _require_admin(request)
    rules = load_rules()
    types_list = rules.get("process_types") or []
    return {
        "ollama_configured": settings.ollama_configured,
        "llm_chat_configured": settings.llm_chat_configured,
        "chat_available": settings.chat_llm_available,
        "feishu_configured": settings.feishu_configured,
        "process_types": [
            {
                "id": t.get("id"),
                "name": t.get("name"),
                "description": t.get("description"),
            }
            for t in types_list
        ],
    }


@router.post("/generate")
def generate(body: GenerateBody, request: Request):
    """根据自然语言描述生成流程文档，返回结构化数据与 Markdown。"""
    _require_admin(request)
    if not settings.chat_llm_available:
        raise HTTPException(
            status_code=503,
            detail="LLM 未配置：请在 .env 设置 LLM_BASE_URL + LLM_MODEL（OpenAI 兼容），或设置 OLLAMA_URL 使用 Ollama。",
        )
    text = (body.natural_language or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="请填写自然语言描述")
    try:
        structured, markdown = generate_process_doc(text, body.process_type_id)
        return {"structured": structured, "markdown": markdown}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("流程文档生成失败")
        raise HTTPException(status_code=500, detail="生成失败，请检查 LLM/Ollama 服务与规则配置")


@router.post("/sync-feishu")
def sync_feishu(body: SyncFeishuBody, request: Request):
    """将流程文档同步到飞书云文档。需配置 FEISHU_APP_ID、FEISHU_APP_SECRET。"""
    _require_admin(request)
    if not settings.feishu_configured:
        raise HTTPException(
            status_code=503,
            detail="飞书未配置，请在 .env 中设置 FEISHU_APP_ID、FEISHU_APP_SECRET 并申请云文档权限",
        )
    try:
        result = sync_doc_to_feishu(body.title or "流程文档", body.markdown or "")
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("同步飞书失败")
        raise HTTPException(status_code=500, detail="同步失败，请检查飞书配置与网络")
