from pathlib import Path

import jwt
from fastapi.testclient import TestClient

from backend.config import settings
from backend.main import app


def _auth_header(username: str) -> dict[str, str]:
    token = jwt.encode({"sub": username}, settings.auth_secret, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def _chat_body(doc_id: str) -> dict:
    return {
        "messages": [{"role": "user", "content": f"请用docling解析 {doc_id}"}],
        "enabled_tools": ["tool.docling.convert"],
    }


def test_ai_interaction_docling_convert_forbidden_if_not_owner(monkeypatch, tmp_path):
    from backend.services import kb_documents
    from backend.routers import ai_interaction as mod

    tenant_id = "tenant1"
    doc_id = "ud_abcdef"
    root = tmp_path / doc_id / "archive"
    root.mkdir(parents=True, exist_ok=True)
    (root / "full.md").write_text("secret", encoding="utf-8")

    monkeypatch.setattr(mod, "load_fixtures", lambda: {"tenant_id": tenant_id})
    monkeypatch.setattr(kb_documents, "_doc_root", lambda _t, _d: Path(tmp_path) / _d)
    monkeypatch.setattr(kb_documents, "get_document_owner", lambda _t, _d: "other_user")

    client = TestClient(app)
    res = client.post("/api/ai-interaction/chat", headers=_auth_header("alice"), json=_chat_body(doc_id))
    assert res.status_code == 200, res.text
    data = res.json()
    assert "Docling" in (data.get("reply") or "")
    assert data.get("tool_calls"), data
    tool_calls = [x for x in (data.get("tool_calls") or []) if x.get("name") == "tool.docling.convert"]
    assert tool_calls, data
    assert tool_calls[0]["ok"] is False


def test_ai_interaction_docling_convert_ok_for_owner(monkeypatch, tmp_path):
    from backend.services import kb_documents
    from backend.routers import ai_interaction as mod

    tenant_id = "tenant1"
    doc_id = "ud_123456"
    root = tmp_path / doc_id / "archive"
    root.mkdir(parents=True, exist_ok=True)
    (root / "full.md").write_text("docling-content", encoding="utf-8")

    monkeypatch.setattr(mod, "load_fixtures", lambda: {"tenant_id": tenant_id})
    monkeypatch.setattr(kb_documents, "_doc_root", lambda _t, _d: Path(tmp_path) / _d)
    monkeypatch.setattr(kb_documents, "get_document_owner", lambda _t, _d: "alice")

    client = TestClient(app)
    res = client.post("/api/ai-interaction/chat", headers=_auth_header("alice"), json=_chat_body(doc_id))
    assert res.status_code == 200, res.text
    data = res.json()
    assert "docling-content" in (data.get("reply") or "")
    assert data.get("tool_calls"), data
    tool_calls = [x for x in (data.get("tool_calls") or []) if x.get("name") == "tool.docling.convert"]
    assert tool_calls, data
    assert tool_calls[0]["ok"] is True

