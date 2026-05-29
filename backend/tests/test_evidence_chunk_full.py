"""RAG 证据送入 LLM 时保持 section 级 chunk 完整（≤ max_section_chars）。"""

from __future__ import annotations

from backend.config import settings
from backend.services import ai_interaction_llm as llm


def test_evidence_chunk_text_not_truncated_under_cap(monkeypatch):
    monkeypatch.setattr(settings, "kb_evidence_chunk_max_chars", 15000)
    body = "营" * 8000 + "\n| 营业收入 | 834527936 |"
    out = llm._evidence_chunk_text_for_llm(body)
    assert out == body
    assert "截断" not in out


def test_evidence_chunk_text_truncates_only_when_over_cap(monkeypatch):
    monkeypatch.setattr(settings, "kb_evidence_chunk_max_chars", 1000)
    body = "x" * 2000
    out = llm._evidence_chunk_text_for_llm(body)
    assert len(out) < len(body)
    assert "截断" in out


def test_generate_answer_with_evidence_includes_full_chunk(monkeypatch):
    monkeypatch.setattr(settings, "kb_evidence_chunk_max_chars", 15000)
    monkeypatch.setattr(settings, "llm_base_url", "http://llm.test/v1")
    monkeypatch.setattr(settings, "llm_model", "test-model")
    long = "营业收入 834527936.00 " + ("明细行 " * 400)
    captured: dict = {}

    def fake_chat(**kwargs):
        captured["messages"] = kwargs.get("messages")
        return {"message": {"content": "ok"}}

    monkeypatch.setattr(llm, "_load_doc_chunk_text", lambda *a, **k: long)
    monkeypatch.setattr(llm, "chat_completions_ollama_shaped", fake_chat)

    llm.generate_answer_with_evidence(
        tenant_id="tenant1",
        model="test",
        user_query="华清25年营收",
        citations=[{"evidence_type": "doc_chunk", "doc_id": "ud_abc", "chunk_id": "s0001"}],
        fixtures={"documents": []},
    )
    user_msg = (captured.get("messages") or [])[-1]["content"]
    assert "834527936" in user_msg
    assert long[:500] in user_msg
