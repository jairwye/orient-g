"""KB 预检索快速路径：避免 Hermes 重复 MCP。"""

from __future__ import annotations

from backend.config import settings
from backend.services.agent_kb_fast_path import (
    comparison_answer_addon,
    prefetch_has_usable_evidence,
    query_implies_kb_write,
    should_use_kb_fast_path,
)


def test_prefetch_has_usable_evidence():
    assert not prefetch_has_usable_evidence(None)
    assert not prefetch_has_usable_evidence({"ok": True, "citations": []})
    assert prefetch_has_usable_evidence({"ok": True, "citations": [{"doc_id": "d1"}]})


def test_should_use_kb_fast_path_when_citations(monkeypatch):
    monkeypatch.setattr(settings, "hermes_agent_kb_fast_path", True)
    monkeypatch.setattr(settings, "hermes_agent_kb_prefetch", True)
    pr = {"ok": True, "citations": [{"doc_id": "d1"}]}
    assert should_use_kb_fast_path(pr, user_query="华清25、24损益对比", allow_kb_write=True)
    assert not should_use_kb_fast_path(
        pr,
        user_query="请上传文件到知识库",
        allow_kb_write=True,
    )


def test_comparison_addon_for_huaqing_query():
    addon = comparison_answer_addon("出具华清25、24两年损益的对比分析表")
    assert addon and "Markdown" in addon


def test_query_implies_kb_write():
    assert query_implies_kb_write("请上传 PDF")
    assert not query_implies_kb_write("华清损益对比")
