from backend.services import rag_audit_bridge as bridge


def test_audit_retrieve_attempt_writes_event(monkeypatch):
    events: list[dict] = []

    def capture(tenant_id, *, username, event_type, query=None, meta=None):
        events.append(
            {
                "tenant_id": tenant_id,
                "username": username,
                "event_type": event_type,
                "query": query,
                "meta": meta or {},
            }
        )

    monkeypatch.setattr(bridge, "write_event", capture)
    bridge.audit_retrieve_attempt(
        "tenant1",
        username="alice",
        query="营收多少",
        meta={"channel": "ai-interaction.chat", "selected_folder_ids": ["f1"]},
    )
    assert len(events) == 1
    assert events[0]["event_type"] == "knowledge.retrieve.attempt"
    assert events[0]["meta"]["channel"] == "ai-interaction.chat"


def test_audit_after_ask_denied_writes_retrieve_deny(monkeypatch):
    events: list[str] = []

    def capture(tenant_id, *, username, event_type, query=None, meta=None):
        events.append(event_type)

    monkeypatch.setattr(bridge, "write_event", capture)
    bridge.audit_after_ask_result(
        "tenant1",
        username="bob",
        query="q",
        result={"denied": True, "deny_reason": "empty_scope"},
    )
    assert events == ["knowledge.retrieve.deny"]


def test_audit_after_ask_success_writes_answer_generate(monkeypatch):
    events: list[str] = []

    def capture(tenant_id, *, username, event_type, query=None, meta=None):
        events.append(event_type)

    monkeypatch.setattr(bridge, "write_event", capture)
    bridge.audit_after_ask_result(
        "tenant1",
        username="bob",
        query="q",
        result={
            "denied": False,
            "citations": [{"doc_id": "ud_1"}, {"table_id": "t1"}],
        },
        extra_meta={"channel": "knowledge.ask"},
    )
    assert events == ["ai.answer.generate"]
    # second call meta checked via full capture in integration test


def test_run_pre_ask_guards_rate_limit_denies(monkeypatch):
    monkeypatch.setattr(bridge, "rate_limit_allow", lambda key: False)
    events: list[str] = []

    def capture(tenant_id, *, username, event_type, query=None, meta=None):
        events.append(event_type)

    monkeypatch.setattr(bridge, "write_event", capture)
    out = bridge.run_pre_ask_guards(
        "tenant1",
        username="u1",
        query="hi",
        rate_limit_key="ai-interaction.chat:t1:u1",
        channel="ai-interaction.chat",
    )
    assert out == "rate_limited"
    assert "ai.answer.deny" in events
