from backend.services import kb_folders as kf


def test_collect_subtree_doc_ids_nested(monkeypatch):
    folders = [
        {"folder_id": "f_root", "parent_folder_id": None},
        {"folder_id": "f_child", "parent_folder_id": "f_root"},
        {"folder_id": "f_grand", "parent_folder_id": "f_child"},
    ]

    resources = {
        "f_root": [{"resource_type": "doc", "resource_id": "ud_root"}],
        "f_child": [{"resource_type": "doc", "resource_id": "ud_child"}],
        "f_grand": [{"resource_type": "doc", "resource_id": "ud_grand"}],
    }

    monkeypatch.setattr(kf, "list_folders", lambda _t: folders)

    def fake_list_user_docs(_tenant_id, *, folder_id):
        return [
            str(r.get("resource_id") or "").strip()
            for r in resources.get(folder_id, [])
            if str(r.get("resource_type") or "") == "doc" and str(r.get("resource_id") or "").strip()
        ]

    monkeypatch.setattr(kf, "list_folder_user_doc_ids", fake_list_user_docs)

    assert kf.collect_subtree_doc_ids("tenant1", "f_root") == ["ud_root", "ud_child", "ud_grand"]
    assert kf.collect_subtree_doc_ids("tenant1", "f_child") == ["ud_child", "ud_grand"]
    assert kf.collect_subtree_doc_ids("tenant1", "f_grand") == ["ud_grand"]


def test_collect_subtree_doc_ids_dedupes(monkeypatch):
    folders = [
        {"folder_id": "f_a", "parent_folder_id": None},
        {"folder_id": "f_b", "parent_folder_id": "f_a"},
    ]
    resources = {
        "f_a": [{"resource_type": "doc", "resource_id": "ud_same"}],
        "f_b": [{"resource_type": "doc", "resource_id": "ud_same"}, {"resource_type": "doc", "resource_id": "ud_b"}],
    }
    monkeypatch.setattr(kf, "list_folders", lambda _t: folders)
    monkeypatch.setattr(
        kf,
        "list_folder_user_doc_ids",
        lambda _t, *, folder_id: [
            str(r.get("resource_id") or "").strip()
            for r in resources.get(folder_id, [])
            if str(r.get("resource_type") or "") == "doc" and str(r.get("resource_id") or "").strip()
        ],
    )

    assert kf.collect_subtree_doc_ids("tenant1", "f_a") == ["ud_same", "ud_b"]


def test_collect_subtree_doc_ids_empty_root():
    assert kf.collect_subtree_doc_ids("tenant1", "") == []
