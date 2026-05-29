"""Hermes HTTP 客户端 URL 与 OpenAI 响应解析。"""

from backend.services import hermes_client as hc


def test_chat_completions_url():
    from backend.config import settings

    old = settings.hermes_base_url
    try:
        settings.hermes_base_url = "http://hermes-agent:8642"
        assert hc._chat_completions_url() == "http://hermes-agent:8642/v1/chat/completions"
        settings.hermes_base_url = "http://hermes-agent:8642/v1"
        assert hc._chat_completions_url() == "http://hermes-agent:8642/v1/chat/completions"
    finally:
        settings.hermes_base_url = old


def test_parse_openai_style_response():
    data = {
        "choices": [
            {
                "message": {
                    "content": "hello",
                    "tool_calls": [{"id": "1", "function": {"name": "orientg_kb_ask"}}],
                }
            }
        ]
    }
    reply = ""
    tool_calls = []
    choices = data.get("choices")
    if choices:
        msg = choices[0].get("message") or {}
        reply = msg.get("content") or ""
        tool_calls = msg.get("tool_calls") or []
    assert reply == "hello"
    assert len(tool_calls) == 1
