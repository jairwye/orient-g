"""Hermes 配置诊断（供 /api/agent/status 与运维排查）。"""

from __future__ import annotations

import os
from typing import Any

from backend.config import _ENV_FILE, settings
from backend.services.hermes_client import fetch_hermes_capabilities, hermes_capabilities_support_runs


def _env_present(key: str) -> bool:
    v = os.environ.get(key)
    return v is not None and str(v).strip() != ""


def diagnose_hermes() -> dict[str, Any]:
    enabled = bool(settings.hermes_enabled)
    base_url = (settings.hermes_base_url or "").strip()
    dev_mock = bool(settings.hermes_dev_mock)
    configured = settings.hermes_configured
    mock_active = dev_mock and not configured

    missing: list[str] = []
    if not enabled and not _env_present("HERMES_ENABLED"):
        missing.append("HERMES_ENABLED")
    elif not enabled and _env_present("HERMES_ENABLED"):
        missing.append("HERMES_ENABLED（环境变量存在但解析为 false，检查取值是否为 true/1）")

    if not base_url and not _env_present("HERMES_BASE_URL"):
        missing.append("HERMES_BASE_URL")

    hints: list[str] = []
    if mock_active:
        hints.append(
            "当前为开发 mock：HERMES_DEV_MOCK=true 且 Hermes HTTP 未配置。"
            " 请在项目根 .env 设 HERMES_ENABLED=true、HERMES_DEV_MOCK=false、HERMES_BASE_URL 后重启 backend（uvicorn 不会热加载 .env）。"
        )
    elif configured:
        hints.append("Hermes HTTP 已配置；请确认 hermes-agent 容器已启动且 /health 可达。")
    elif enabled and base_url:
        hints.append("HERMES_ENABLED 与 HERMES_BASE_URL 已设置；若仍失败请检查 backend 是否已重建/拉取含 Hermes 集成的新镜像。")
    elif enabled:
        hints.append("已设置 HERMES_ENABLED=true，但缺少有效的 HERMES_BASE_URL（例：http://hermes-agent:8642）。")
    else:
        hints.append(
            "生产：在部署目录 .env 设置 HERMES_ENABLED=true、HERMES_BASE_URL，并 docker compose up -d backend。"
        )
        hints.append("开发环境见 docs/hermes.md §2；可选 L0 mock：HERMES_DEV_MOCK=true（§4）。")

    caps: dict = {}
    runs_api_ready = False
    if configured:
        caps = fetch_hermes_capabilities()
        runs_api_ready = hermes_capabilities_support_runs(caps)

    return {
        "hermes_enabled": enabled,
        "hermes_base_url_set": bool(base_url),
        "hermes_configured": configured,
        "hermes_dev_mock": dev_mock,
        "hermes_dev_mock_active": mock_active,
        "hermes_agent_kb_prefetch": bool(settings.hermes_agent_kb_prefetch),
        "hermes_agent_kb_synthesize": bool(settings.hermes_agent_kb_synthesize),
        "hermes_agent_kb_fast_path": bool(settings.hermes_agent_kb_fast_path),
        "agent_router_enabled": True,
        "agent_route_default": (settings.hermes_agent_route_default or "tier0").strip(),
        "hermes_agent_kb_multi_query": bool(getattr(settings, "hermes_agent_kb_multi_query", True)),
        "effective_kb_multi_query": bool(settings.effective_kb_multi_query),
        "kb_multi_query": settings.kb_multi_query,
        "hermes_agent_standard_tier0": bool(getattr(settings, "hermes_agent_standard_tier0", True)),
        "hermes_agent_kb_ask_budget_lite": int(settings.hermes_agent_kb_ask_budget_lite or 2),
        "hermes_agent_simple_query_fast": bool(settings.hermes_agent_simple_query_fast),
        "hermes_agent_stream": bool(settings.hermes_agent_stream),
        "hermes_agent_use_runs_api": bool(settings.hermes_agent_use_runs_api),
        "hermes_capabilities": caps,
        "hermes_runs_api_ready": runs_api_ready,
        "kb_evidence_chunk_max_chars": int(settings.kb_evidence_chunk_max_chars or 15000),
        "env_hermes_enabled_present": _env_present("HERMES_ENABLED"),
        "env_hermes_base_url_present": _env_present("HERMES_BASE_URL"),
        "env_file_path": str(_ENV_FILE),
        "env_file_exists": _ENV_FILE.is_file(),
        "missing": missing,
        "hints": hints,
        "ready_for_agent_chat": configured or mock_active,
    }
