"""Orient-G MCP 工具：ACL 与审计。"""

import base64
import time

import jwt
import pytest

from backend.config import settings
from backend.services import orientg_mcp_tools as mcp_tools


def _token(sub: str = "admin") -> str:
    payload = {"sub": sub, "iat": int(time.time()), "exp": int(time.time()) + 3600}
    return jwt.encode(payload, settings.auth_secret, algorithm="HS256")


def test_kb_ask_delegates_to_pipeline(monkeypatch):
    captured = {}

    def fake_ask(token, query, **kwargs):
        captured["token"] = token
        captured["query"] = query
        return {"denied": False, "reply": "stub-reply", "citations": [{"doc_id": "ud_x"}]}

    events: list[str] = []
    monkeypatch.setattr("backend.services.orientg_mcp_tools.ask_knowledge", fake_ask)
    monkeypatch.setattr(
        "backend.services.orientg_mcp_tools.write_event",
        lambda *a, **k: events.append(k.get("event_type") or ""),
    )

    tok = _token()
    out = mcp_tools.orientg_kb_ask(tok, "合同条款是什么？")
    assert out["ok"] is True
    assert out["reply"] == "stub-reply"
    assert captured["query"] == "合同条款是什么？"
    assert "hermes.mcp.orientg_kb_ask" in events


def test_kb_assign_denies_when_doc_not_writable(monkeypatch):
    monkeypatch.setattr(
        "backend.services.orientg_mcp_tools.compute_acl_scope",
        lambda *a, **k: {
            "allowed_doc_ids": ["ud_other"],
            "writable_doc_ids": [],
            "writable_collection_ids": [],
            "allowed_collection_ids": [],
        },
    )
    monkeypatch.setattr("backend.services.orientg_mcp_tools.write_event", lambda *a, **k: None)

    out = mcp_tools.orientg_kb_assign(_token(), doc_id="ud_other", collection_ids=["c_finance_public_1"])
    assert out.get("denied") is True
    assert out.get("reason") == "doc_not_writable"


def test_kb_upload_queues_document(monkeypatch):
    monkeypatch.setattr(
        "backend.services.orientg_mcp_tools.compute_acl_scope",
        lambda *a, **k: {
            "writable_collection_ids": ["c_private_admin"],
            "writable_doc_ids": [],
        },
    )
    monkeypatch.setattr(
        "backend.services.orientg_mcp_tools.kb_docs.upload_user_document_async",
        lambda *a, **k: {"doc_id": "ud_test1", "status": "queued"},
    )
    monkeypatch.setattr(
        "backend.services.orientg_mcp_tools.enqueue_user_doc_task",
        lambda *a, **k: (True, None),
    )
    monkeypatch.setattr("backend.services.orientg_mcp_tools.write_event", lambda *a, **k: None)

    raw = b"# hello"
    out = mcp_tools.orientg_kb_upload(
        _token(),
        filename="note.md",
        content_base64=base64.b64encode(raw).decode("ascii"),
    )
    assert out["ok"] is True
    assert out["doc_id"] == "ud_test1"
