"""多 query 检索与 pack 组装（mock ask）。"""

from __future__ import annotations

from unittest.mock import patch

from backend.services.kb_retrieve_pack import retrieve_kb_evidence_pack


def test_multi_query_merges_citations():
    calls: list[str] = []

    def _fake_ask(_token, query, ask_kwargs=None):
        calls.append(query)
        if "销售费用" in query:
            return {
                "ok": True,
                "citations": [{"doc_id": "ud_fee", "chunk_id": "c_fee"}],
                "reply": "fee hit",
            }
        return {
            "ok": True,
            "citations": [{"doc_id": "ud_pl", "chunk_id": "c_pl"}],
            "reply": "pl hit",
        }

    with patch("backend.services.kb_retrieve_pack.execute_kb_subquery_ask", side_effect=_fake_ask):
        result, tools = retrieve_kb_evidence_pack(
            "token",
            "可比公司E成本明细分解",
            {"selected_folder_ids": ["f1"]},
            fixtures={"tenant_id": "tenant1", "documents": []},
            multi_query=True,
            resolved_scope={
                "collection_ids": [],
                "attached_doc_ids": ["ud_pl"],
                "limit_to_attached": True,
            },
        )
    assert result.get("ok")
    assert len(calls) >= 2
    ids = {c.get("doc_id") for c in result.get("citations") or []}
    assert "ud_fee" in ids
    assert "ud_pl" in ids
    assert result.get("evidence_pack")
    assert len(tools) == len(calls)


def test_partial_subquery_denied_merges_ok_results():
    calls: list[str] = []

    def _fake_ask(_token, query, ask_kwargs=None):
        calls.append(query)
        if "销售费用" in query:
            return {"denied": True, "deny_reason": "no access"}
        return {
            "ok": True,
            "citations": [{"doc_id": "ud_ok", "chunk_id": "c1"}],
            "reply": "ok",
        }

    with patch("backend.services.kb_retrieve_pack.execute_kb_subquery_ask", side_effect=_fake_ask):
        result, tools = retrieve_kb_evidence_pack(
            "token",
            "成本明细",
            {},
            fixtures={"tenant_id": "tenant1", "documents": []},
            multi_query=True,
            resolved_scope={
                "collection_ids": [],
                "attached_doc_ids": [],
                "limit_to_attached": False,
            },
        )
    assert result.get("ok")
    assert result.get("partial_denied") is True
    assert any(c.get("doc_id") == "ud_ok" for c in (result.get("citations") or []))
    assert any(t.get("status") == "denied" for t in tools)
    assert "部分子检索" in " ".join(result.get("evidence_pack", {}).get("gaps") or [])


def test_native_full_personnel_slim_prefetch_caps_subqueries(monkeypatch):
    """目标 4：native+full+人员 预检索子检索 ≤ HERMES_NATIVE_PREFETCH_MAX_KB_ASKS。"""
    from backend.config import settings

    monkeypatch.setattr(settings, "hermes_native_mcp_reply", True)
    monkeypatch.setattr(settings, "hermes_native_prefetch_max_kb_asks", 1)
    calls: list[str] = []

    def _fake_ask(_token, query, ask_kwargs=None):
        calls.append(query)
        return {
            "ok": True,
            "citations": [{"doc_id": "ud_p", "chunk_id": "c1"}],
            "reply": "personnel hit",
        }

    q = "对比分析YYCQ和可比公司A25年的人员结构"
    with patch("backend.services.kb_retrieve_pack.execute_kb_subquery_ask", side_effect=_fake_ask):
        result, tools = retrieve_kb_evidence_pack(
            "token",
            q,
            {"selected_folder_ids": ["f1"]},
            fixtures={"tenant_id": "tenant1", "documents": []},
            multi_query=True,
            prefetch_tier="full",
            resolved_scope={
                "collection_ids": [],
                "attached_doc_ids": [],
                "limit_to_attached": False,
                "folder_ids": ["f1"],
            },
        )
    assert result.get("ok")
    assert len(calls) <= 1
    assert len(tools) <= 1
    assert len(calls) >= 1
    assert calls[0] == q


def test_native_full_personnel_prefetch_zero_skips_kb_asks(monkeypatch):
    from backend.config import settings

    monkeypatch.setattr(settings, "hermes_native_mcp_reply", True)
    monkeypatch.setattr(settings, "hermes_native_prefetch_max_kb_asks", 0)
    calls: list[str] = []

    def _fake_ask(_token, query, ask_kwargs=None):
        calls.append(query)
        return {"ok": True, "citations": [], "reply": ""}

    with patch("backend.services.kb_retrieve_pack.execute_kb_subquery_ask", side_effect=_fake_ask):
        result, tools = retrieve_kb_evidence_pack(
            "token",
            "对比分析YYCQ和可比公司A25年的人员结构",
            {"selected_folder_ids": ["f1"]},
            fixtures={"tenant_id": "tenant1", "documents": []},
            multi_query=True,
            prefetch_tier="full",
            resolved_scope={
                "collection_ids": [],
                "attached_doc_ids": [],
                "limit_to_attached": False,
                "folder_ids": ["f1"],
            },
        )
    assert result.get("ok")
    assert calls == []
    assert tools == []
    assert result.get("native_slim_prefetch") is True
    assert result.get("evidence_pack")


def test_legacy_full_personnel_still_multi_query(monkeypatch):
    """非 native：deep 人员仍允许多 query（回归）。"""
    from backend.config import settings

    monkeypatch.setattr(settings, "hermes_native_mcp_reply", False)
    calls: list[str] = []

    def _fake_ask(_token, query, ask_kwargs=None):
        calls.append(query)
        return {
            "ok": True,
            "citations": [{"doc_id": "ud_p", "chunk_id": "c1"}],
            "reply": "ok",
        }

    with patch("backend.services.kb_retrieve_pack.execute_kb_subquery_ask", side_effect=_fake_ask):
        _result, tools = retrieve_kb_evidence_pack(
            "token",
            "对比分析YYCQ和可比公司A25年的人员结构",
            {"selected_folder_ids": ["f1"]},
            fixtures={"tenant_id": "tenant1", "documents": []},
            multi_query=True,
            prefetch_tier="full",
            resolved_scope={
                "collection_ids": [],
                "attached_doc_ids": [],
                "limit_to_attached": False,
                "folder_ids": ["f1"],
            },
        )
    assert len(calls) >= 3
    assert len(tools) == len(calls)
