from types import SimpleNamespace

from backend.routers import knowledge


class _Req(SimpleNamespace):
    headers: dict


def test_parse_folder_enqueues_docs(monkeypatch):
    # auth
    monkeypatch.setattr(knowledge, "_get_username_from_request", lambda _req: "u1")
    monkeypatch.setattr(knowledge, "_get_token_from_request", lambda _req: "tok")
    monkeypatch.setattr(knowledge, "load_fixtures", lambda: {"tenant_id": "tenant1"})
    monkeypatch.setattr(knowledge, "compute_acl_scope", lambda _tok, fixtures=None: {"allowed_collection_ids": ["c1"], "allowed_table_ids": []})

    # folder + resources
    monkeypatch.setattr(
        knowledge,
        "get_folder",
        lambda _tid, folder_id: {"folder_id": folder_id, "owner_username": None, "collection_ids": ["c1"]},
    )
    monkeypatch.setattr(
        knowledge,
        "list_folder_resources",
        lambda _tid, folder_id: [
            {"resource_type": "doc", "resource_id": "ud_a"},
            {"resource_type": "doc", "resource_id": "ud_b"},
            {"resource_type": "table", "resource_id": "t1"},
        ],
    )
    called: list[str] = []

    def fake_enqueue(tid: str, un: str, doc_id: str):
        called.append(doc_id)
        return True, None

    monkeypatch.setattr(knowledge, "enqueue_user_doc_task", fake_enqueue)
    res = knowledge.kb_parse_folder("f1", _Req(headers={}))
    assert res["ok"] is True
    assert res["queued"] == 2
    assert set(called) == {"ud_a", "ud_b"}


def test_parse_folder_forbidden_when_not_visible(monkeypatch):
    monkeypatch.setattr(knowledge, "_get_username_from_request", lambda _req: "u2")
    monkeypatch.setattr(knowledge, "_get_token_from_request", lambda _req: "tok")
    monkeypatch.setattr(knowledge, "load_fixtures", lambda: {"tenant_id": "tenant1"})
    monkeypatch.setattr(knowledge, "compute_acl_scope", lambda _tok, fixtures=None: {"allowed_collection_ids": [], "allowed_table_ids": []})
    monkeypatch.setattr(
        knowledge,
        "get_folder",
        lambda _tid, folder_id: {"folder_id": folder_id, "owner_username": None, "collection_ids": ["c_secret"]},
    )
    try:
        knowledge.kb_parse_folder("f_secret", _Req(headers={}))
        assert False, "should raise"
    except Exception as e:
        assert "forbidden" in str(e).lower()

