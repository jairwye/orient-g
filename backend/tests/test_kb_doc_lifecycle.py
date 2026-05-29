import pytest

from backend.services.kb_doc_lifecycle import (
    ALLOWED_TRANSITIONS,
    InvalidDocStatusTransition,
    can_transition,
    transition_document_status,
)


def test_can_transition_uploaded_to_parsed():
    assert can_transition("uploaded", "parsed") is True


def test_can_transition_rejects_active_to_uploaded():
    assert can_transition("active", "uploaded") is False


def test_invalid_transition_raises():
    with pytest.raises(InvalidDocStatusTransition):
        can_transition("failed", "packaged", raise_on_invalid=True)


def test_allowed_transitions_cover_pipeline():
    assert "uploaded" in ALLOWED_TRANSITIONS
    assert "parsed" in ALLOWED_TRANSITIONS["uploaded"]
    assert "active" in ALLOWED_TRANSITIONS["packaged"]


def test_transition_document_status_calls_db(monkeypatch):
    calls: list[tuple[str, str]] = []

    def fake_update(tenant_id: str, doc_id: str, status: str, **kwargs):
        calls.append((doc_id, status))

    monkeypatch.setattr(
        "backend.services.kb_doc_lifecycle._update_status_row",
        fake_update,
    )
    transition_document_status("t1", "ud_x", "parsed", from_status="uploaded")
    assert calls == [("ud_x", "parsed")]


def test_transition_document_status_validates_from_status(monkeypatch):
    monkeypatch.setattr(
        "backend.services.kb_doc_lifecycle._update_status_row",
        lambda *a, **k: None,
    )
    with pytest.raises(InvalidDocStatusTransition):
        transition_document_status("t1", "ud_x", "active", from_status="uploaded")
