"""
OpenAI 兼容 Chat Completions（/v1/chat/completions）。

用于对话/工具调用等路径；与 Ollama 的 /api/chat 响应形态不同，此处归一化为 Ollama 风格顶层字段，
便于现有业务代码继续读取 resp["message"]。
"""

from __future__ import annotations

from typing import Any

from backend.config import settings
from backend.services.ollama_guard import post_json_with_guard
from backend.services.upstream_guard import assert_upstream_allowed


def llm_chat_completions_url() -> str:
    """返回完整 chat completions URL（含 /v1 前缀）。"""
    raw = (settings.llm_base_url or "").strip().rstrip("/")
    if not raw:
        raise ValueError("LLM 未配置：请在 .env 中设置 LLM_BASE_URL")
    if raw.endswith("/v1"):
        return f"{raw}/chat/completions"
    return f"{raw}/v1/chat/completions"


def _llm_auth_headers() -> dict[str, str] | None:
    key = (settings.llm_api_key or "").strip()
    if not key:
        return None
    return {"Authorization": f"Bearer {key}"}


def _normalize_openai_chat_response(data: dict[str, Any]) -> dict[str, Any]:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("LLM 响应缺少 choices")
    ch0 = choices[0]
    if not isinstance(ch0, dict):
        raise RuntimeError("LLM 响应 choices[0] 无效")
    msg = ch0.get("message")
    if not isinstance(msg, dict):
        raise RuntimeError("LLM 响应缺少 message")
    # 与 Ollama /api/chat 对齐：顶层 message
    return {"message": msg, "model": data.get("model"), "done": True}


def chat_completions_ollama_shaped(
    *,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    model: str,
    timeout_s: float,
    kind: str,
) -> dict[str, Any]:
    """
    POST /v1/chat/completions，返回与 Ollama /api/chat 兼容的顶层结构（含 message）。
    """
    url = llm_chat_completions_url()
    assert_upstream_allowed(url, service_name="LLM")
    payload: dict[str, Any] = {
        "model": (model or "").strip() or (settings.llm_model or "").strip(),
        "messages": messages,
        "stream": False,
    }
    if tools:
        payload["tools"] = tools
    raw = post_json_with_guard(
        url=url,
        payload=payload,
        timeout_s=timeout_s,
        kind=kind,
        headers=_llm_auth_headers(),
        circuit_scope="llm",
    )
    return _normalize_openai_chat_response(raw)
