"""AI 互动 chat 路径应写入与 /knowledge/ask 一致的审计事件。"""

import time

import jwt
import pytest
from fastapi.testclient import TestClient

from backend.config import Settings, settings
from backend.main import app


def _token(sub: str = "admin") -> str:
    payload = {"sub": sub, "iat": int(time.time()), "exp": int(time.time()) + 3600}
    return jwt.encode(payload, settings.auth_secret, algorithm="HS256")


@pytest.fixture
def client():
    return TestClient(app)


def test_ai_chat_kb_scope_writes_audit_events(client, monkeypatch):
    events: list[str] = []

    def capture(tenant_id, *, username, event_type, query=None, meta=None):
        events.append(event_type)

    monkeypatch.setattr(
        "backend.services.rag_audit_bridge.write_event",
        capture,
    )
    monkeypatch.setattr(
        "backend.services.knowledge_pipeline.ask_knowledge",
        lambda *a, **k: {
            "denied": False,
            "reply": "stub",
            "citations": [{"doc_id": "ud_test", "chunk_id": "c1"}],
        },
    )
    monkeypatch.setattr(
        Settings,
        "chat_llm_available",
        property(lambda self: False),
    )

    r = client.post(
        "/api/ai-interaction/chat",
        headers={"Authorization": f"Bearer {_token()}"},
        json={
            "messages": [{"role": "user", "content": "测试审计"}],
            "kb_scope": {"selected_collection_ids": ["c_finance_public_1"]},
        },
    )
    assert r.status_code == 200
    assert "knowledge.retrieve.attempt" in events
    assert "ai.answer.generate" in events
