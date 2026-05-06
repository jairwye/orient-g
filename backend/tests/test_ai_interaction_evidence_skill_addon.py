"""generate_answer_with_evidence 在 KB 路径下注入 skill_addon。"""
from __future__ import annotations

from unittest.mock import patch

from backend.services.ai_interaction_llm import generate_answer_with_evidence


def test_evidence_path_includes_skill_addon_in_system():
    captured: dict = {}

    def fake_post(*, url, payload, timeout_s, kind, **kwargs):
        captured["payload"] = payload
        return {"message": {"content": "ok"}}

    def fake_chat_completions(*, messages, tools, model, timeout_s, kind):
        # OpenAI 兼容路径：与 Ollama /api/chat 归一后的结构一致（见 generate_answer_with_evidence）
        captured["payload"] = {"messages": messages}
        return {"message": {"content": "ok"}}

    with patch(
        "backend.services.ai_interaction_llm.chat_completions_ollama_shaped",
        side_effect=fake_chat_completions,
    ):
        with patch("backend.services.ai_interaction_llm.post_json_with_guard", side_effect=fake_post):
            with patch("backend.services.ai_interaction_llm._ollama_base", return_value="http://127.0.0.1:11434"):
                out = generate_answer_with_evidence(
                    tenant_id="tenant1",
                    model="m",
                    user_query="q",
                    citations=[],
                    fixtures={},
                    skill_addon="## 测试技能\n只作补充。",
                )
    assert out == "ok"
    msgs = captured["payload"]["messages"]
    assert msgs[0]["role"] == "system"
    sys = msgs[0]["content"]
    assert "财务知识库问答助手" in sys
    assert "仅依据证据" in sys or "证据" in sys
    assert "## 测试技能" in sys
    assert "只作补充" in sys
