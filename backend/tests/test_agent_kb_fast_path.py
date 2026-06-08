"""KB 预检索快速路径：避免 Hermes 重复 MCP。"""

from __future__ import annotations

from unittest.mock import patch

from backend.config import settings
from backend.services.agent_kb_fast_path import (
    comparison_answer_addon,
    finalize_fast_path_reply,
    prefetch_has_usable_evidence,
    query_implies_kb_write,
    should_use_kb_fast_path,
    stream_kb_fast_path_events,
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
    addon = comparison_answer_addon("出具华清25、24两年损益的对比分析表", tier="local")
    assert addon and "Markdown" in addon


def test_query_implies_kb_write():
    assert query_implies_kb_write("请上传 PDF")
    assert not query_implies_kb_write("华清损益对比")


def test_finalize_fast_path_reply_strips_inline_ud_ids():
    ud = "ud_0401544fb6f7425092db1d9f7a970917"
    raw = f"结论：研发费用 8,851,536.62 ({ud})\n| 2025 | 8,851,536.62 |"
    out = finalize_fast_path_reply(raw, user_query="华清25、24研发费用对比")
    assert ud not in out
    assert "8,851,536.62" in out


@patch("backend.services.agent_kb_prefetch.synthesize_kb_reply")
def test_stream_fast_path_finalizes_reply(mock_synth):
    ud = "ud_0401544fb6f7425092db1d9f7a970917"
    mock_synth.return_value = {
        "reply": f"结论：费用 1,234,567.89 ({ud})\n",
        "citations": [{"doc_id": "d1"}],
        "synthesis": "local",
    }
    prefetch = {
        "ok": True,
        "citations": [{"doc_id": "d1"}],
        "evidence_pack": {"task_type": "compare", "coverage_score": 1.0},
    }
    events = list(
        stream_kb_fast_path_events(
            tenant_id="t1",
            user_query="华清25、24研发费用对比",
            prefetch_result=prefetch,
            prefetch_tool_calls=[],
            fixtures={"tenant_id": "t1"},
        )
    )
    done = next(e for e in events if e.get("type") == "done")
    assert ud not in (done.get("reply") or "")
    assert "1,234,567.89" in (done.get("reply") or "")
