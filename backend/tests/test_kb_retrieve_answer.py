"""统一检索入口 kb_retrieve_answer。"""

from __future__ import annotations

from unittest.mock import patch

from backend.config import settings
from backend.services.kb_retrieve_answer import kb_multi_query_enabled, retrieve_and_answer


def test_kb_multi_query_respects_kb_multi_query_env(monkeypatch):
    monkeypatch.setattr(settings, "kb_multi_query", False, raising=False)
    monkeypatch.setattr(settings, "hermes_agent_kb_multi_query", True, raising=False)
    assert kb_multi_query_enabled() is False


def test_kb_multi_query_falls_back_to_hermes_flag(monkeypatch):
    monkeypatch.setattr(settings, "kb_multi_query", None, raising=False)
    monkeypatch.setattr(settings, "hermes_agent_kb_multi_query", False, raising=False)
    assert kb_multi_query_enabled() is False


def test_retrieve_and_answer_delegates():
    fake = ({"ok": True, "citations": [], "evidence_pack": {"version": 1}}, [])
    with patch(
        "backend.services.kb_retrieve_answer.retrieve_kb_evidence_pack",
        return_value=fake,
    ) as m:
        out = retrieve_and_answer("tok", "q", {}, multi_query=False)
    assert out == fake
    m.assert_called_once()
    assert m.call_args.kwargs.get("multi_query") is False
