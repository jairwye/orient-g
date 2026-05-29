"""kb_scope folder_ids 解析（Agent / 预检索与 AI 互动对齐）。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from backend.services.kb_scope_resolve import resolve_kb_scope_for_ask


def test_resolve_folder_expands_collections_and_docs(monkeypatch):
    import backend.services.kb_folders as kf

    monkeypatch.setattr(
        kf,
        "list_folders",
        lambda tenant_id: [{"folder_id": "f_pub", "collection_ids": ["c_finance_public_1"]}],
    )
    monkeypatch.setattr(
        kf,
        "collect_subtree_doc_ids",
        lambda tenant_id, fid: ["ud_huaqing25"] if fid == "f_pub" else [],
    )

    out = resolve_kb_scope_for_ask(
        "tenant1",
        {"selected_folder_ids": ["f_pub"]},
        attached_doc_ids=[],
    )
    assert "c_finance_public_1" in out["collection_ids"]
    assert "ud_huaqing25" in out["attached_doc_ids"]
    assert out["limit_to_attached"] is True


def test_resolve_explicit_collection_not_limit_to_attached(monkeypatch):
    import backend.services.kb_folders as kf

    monkeypatch.setattr(
        kf,
        "list_folders",
        lambda tenant_id: [{"folder_id": "f_pub", "collection_ids": ["c_finance_public_1"]}],
    )
    monkeypatch.setattr(kf, "collect_subtree_doc_ids", lambda tenant_id, fid: ["ud_x"])

    out = resolve_kb_scope_for_ask(
        "tenant1",
        {
            "selected_folder_ids": ["f_pub"],
            "selected_collection_ids": ["c_finance_public_1"],
        },
    )
    assert out["limit_to_attached"] is False
