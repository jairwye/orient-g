"""Hermes MCP 子进程回调：解析 session_key → JWT / kb_scope / 预算（内网，共享密钥）。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from backend.config import settings
from backend.services import hermes_session_context as session_ctx
from backend.services import hermes_token_bridge as bridge
from backend.services import kb_ask_budget as budget

router = APIRouter(prefix="/internal/hermes", tags=["internal-hermes"])


class SessionResolveBody(BaseModel):
    hermes_session_key: str = Field(min_length=1)


class KbAskBudgetBody(BaseModel):
    hermes_session_key: str = Field(min_length=1)


def _expected_bridge_secret() -> str:
    dedicated = (settings.orientg_mcp_bridge_secret or "").strip()
    if dedicated:
        return dedicated
    # 生产必须配置专用桥密钥，禁止回退 AUTH_SECRET
    env = (settings.app_env or "").strip().lower()
    if env in ("production", "prod"):
        return ""
    return (settings.auth_secret or "").strip()


def verify_mcp_bridge_secret(
    x_orientg_mcp_bridge_secret: Annotated[str | None, Header(alias="X-OrientG-MCP-Bridge-Secret")] = None,
) -> None:
    expected = _expected_bridge_secret()
    got = (x_orientg_mcp_bridge_secret or "").strip()
    if not expected or got != expected:
        raise HTTPException(
            status_code=403,
            detail={"code": "bridge_secret_invalid", "message": "invalid MCP bridge secret"},
        )


@router.post("/session/resolve")
def resolve_session(
    body: SessionResolveBody,
    _: Annotated[None, Depends(verify_mcp_bridge_secret)] = None,
):
    key = bridge.normalize_session_key(body.hermes_session_key)
    token = bridge.resolve(key)
    if not token:
        raise HTTPException(
            status_code=404,
            detail={"code": "session_not_found", "message": "session_key not registered or expired"},
        )
    ctx = session_ctx.resolve(key)
    kb_scope = ctx.kb_scope if ctx else {}
    if not kb_scope:
        from backend.services.hermes_shared_session import load_session

        row = load_session(key)
        if row and isinstance(row.get("kb_scope"), dict):
            kb_scope = row.get("kb_scope") or {}
    return {
        "ok": True,
        "user_token": token,
        "kb_scope": kb_scope,
        "allow_kb_write": bool(ctx.allow_kb_write) if ctx else False,
        "orientg_route": ctx.orientg_route if ctx else None,
        "native_mcp_reply": bool(ctx.native_mcp_reply) if ctx else bool(settings.hermes_native_mcp_reply),
    }


@router.post("/session/kb-ask-budget/consume")
def consume_kb_ask_budget(
    body: KbAskBudgetBody,
    _: Annotated[None, Depends(verify_mcp_bridge_secret)] = None,
):
    deny = budget.check_and_consume_ask(body.hermes_session_key)
    if deny:
        return {"ok": False, "denied": True, "reason": deny}
    return {"ok": True, "denied": False}
