"""
数据解析 API：上传 Excel → 解析 → 看板/解读 → 自然语言问答与按需生图/生表。

合规说明（与 规则/规则.md 对齐）：
- 仅内网服务，不暴露公网；Excel 仅上传至本机/内网，无第三方数据上传。
- LLM 仅调用本地 Ollama（OLLAMA_URL），不依赖公网 AI。
- 技术栈为成熟开源（openpyxl、Recharts 等），代码可继承。
"""
import logging

import jwt
from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from backend.config import settings
from backend.services import data_parse_chat
from backend.services.data_parse import run_pipeline
from backend.services.data_parse_chat import _load_skills, _get_tools_def, _build_system_prompt
from backend.services.data_parse_session import create_session, get_session
from backend.services.kb_tables import create_table_instance_from_rows

logger = logging.getLogger(__name__)

router = APIRouter()
ALGORITHM = "HS256"


class ChatBody(BaseModel):
    session_id: str
    extra_session_ids: list[str] | None = Field(default=None, description="可选：附加会话 ID（多 Excel 并存时使用）")
    message: str
    enabled_skills: list[str] | None = Field(default=None, description="工作流传入：数据解析类技能（如 Playbook）")
    prompt_addon: str | None = Field(default=None, description="工作流传入：prompt.* 勾选项拼接的 system 补充，服务端截断")


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


PREVIEW_ROWS = 50


def _tables_preview(tables: dict) -> dict[str, dict]:
    """从 tables 截取前 PREVIEW_ROWS 行作为预览，供前端展示。"""
    out = {}
    for name, t in (tables or {}).items():
        headers = t.get("headers") or []
        rows = (t.get("rows") or [])[:PREVIEW_ROWS]
        out[name] = {"headers": headers, "rows": [[str(c) if c is not None else "" for c in row] for row in rows]}
    return out


@router.post("/upload")
async def upload_excel(file: UploadFile = File(...)):
    """
    上传 Excel（任意格式），执行校验→通用解析，创建 session。
    返回 session_id、table_schemas、tables_preview、kanban_config、analysis。
    """
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="请上传 .xlsx 或 .xls 文件")
    content = await file.read()
    try:
        pipeline_result = run_pipeline(content, file.filename or "upload.xlsx")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    session_id = create_session(pipeline_result)
    analysis = ""
    if settings.ollama_configured:
        try:
            analysis = data_parse_chat.generate_analysis(session_id)
        except Exception as e:
            logger.warning("首轮解读失败: %s", e)
            analysis = "解读生成失败，请检查 Ollama 服务。"
    return {
        "session_id": session_id,
        "table_schemas": pipeline_result.get("table_schemas") or [],
        "tables_preview": _tables_preview(pipeline_result.get("tables") or {}),
        "kanban_config": pipeline_result.get("kanban_config") or [],
        "analysis": analysis,
    }


@router.get("/session/{session_id}")
def get_session_data(session_id: str):
    """返回该 session 的 table_schemas、tables_preview、kanban_config。"""
    s = get_session(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")
    return {
        "table_schemas": s.get("table_schemas") or [],
        "tables_preview": _tables_preview(s.get("tables") or {}),
        "kanban_config": s.get("kanban_config") or [],
    }


class PersistTableBody(BaseModel):
    session_id: str
    sheet_name: str
    name: str | None = None


@router.post("/persist-table")
def persist_table(request: Request, body: PersistTableBody):
    """
    将某个 session 的指定 sheet 持久化为 TableInstance（进入个人私有知识库）。
    """
    un = _get_username_from_request(request)
    if not un:
        raise HTTPException(status_code=401, detail="not authenticated")
    s = get_session(body.session_id)
    if not s:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")
    tables = s.get("tables") or {}
    sheet = tables.get(body.sheet_name or "")
    if not isinstance(sheet, dict):
        raise HTTPException(status_code=404, detail="sheet not found")
    headers = sheet.get("headers") or []
    rows = sheet.get("rows") or []
    if not headers or not rows:
        raise HTTPException(status_code=400, detail="empty table")

    # 单租户：当前 fixtures/系统默认 tenant1
    tenant_id = "tenant1"
    info = create_table_instance_from_rows(
        tenant_id,
        un,
        name=body.name or f"表-{body.sheet_name}",
        source_type="excel_session",
        source_ref=body.session_id,
        headers=headers,
        rows=rows,
        assign_to_private=True,
    )
    return {"ok": True, **info}


@router.post("/chat")
def chat_endpoint(body: ChatBody):
    """自然语言问答；返回 reply、chart_spec、table_spec（可选）。"""
    if not settings.ollama_configured:
        raise HTTPException(status_code=503, detail="Ollama 未配置，请在 .env 中设置 OLLAMA_URL 后使用对话功能")
    extra = [str(x).strip() for x in (body.extra_session_ids or []) if str(x).strip()]
    session_ids = [str(body.session_id).strip(), *extra]
    result = data_parse_chat.chat_multi(
        session_ids,
        body.message,
        enabled_skills=body.enabled_skills,
        prompt_addon=body.prompt_addon,
    )
    return result


@router.get("/status")
def status():
    """供前端判断 Ollama 是否可用（对话与解读依赖）。"""
    return {"ollama_configured": settings.ollama_configured}


@router.get("/prompt-summary")
def prompt_summary():
    """列示：使用的 Prompt 摘要（不暴露完整可执行串）。"""
    _load_skills()  # 确保 skills 可加载，列示不返回完整 system 串
    return {
        "system_summary": "角色：经营数据解析助手。约束：仅根据工具返回的指标与表格作答，禁止编造数值。可输出结论、风险、建议及图表/表格规约。",
        "user_summary": "根据 read_metrics 与用户问题作答；若用户要求画图或制表则调用 generate_chart / generate_table。",
    }


@router.get("/tools")
def tools_list():
    """列示：使用的工具（MCP 风格）及用途与约束。"""
    defs = _get_tools_def()
    return {
        "tools": [
            {"name": f["function"]["name"], "description": f["function"]["description"], "constraint": "只读/仅渲染、不编造"}
            for f in defs
        ]
    }


@router.get("/skills")
def skills_list():
    """列示：Skills 分类与摘要（条数）。"""
    skills = _load_skills()
    return {
        "industry_terms": {"count": len(skills.get("industry_terms") or []), "summary": "行业口径（流水、净利润、同比/环比等）"},
        "finance_terms": {"count": len(skills.get("finance_terms") or []), "summary": "财务术语（本年累计、目标、海外占比等）"},
        "table_display_rules": {"count": len(skills.get("table_display_rules") or []), "summary": "表格规范与展示口径"},
        "exception_templates": {"count": len(skills.get("exception_templates") or []), "summary": "异常解释与风险话术模板"},
    }