"""文件夹 doc 计数应与 kb_user_documents 中可见文档一致（不含 rp_* 占位绑定）。"""

from backend.services import kb_folders as kf


def test_collect_subtree_ignores_non_user_doc_bindings(monkeypatch):
    folders = [{"folder_id": "f1", "parent_folder_id": None}]
    monkeypatch.setattr(kf, "list_folders", lambda _t: folders)
    monkeypatch.setattr(kf, "list_folder_user_doc_ids", lambda _t, *, folder_id: [] if folder_id == "f1" else [])

    assert kf.collect_subtree_doc_ids("tenant1", "f1") == []


def test_list_folder_user_doc_ids_delegates_to_db(monkeypatch):
    monkeypatch.setattr(kf, "list_folder_user_doc_ids", lambda _t, *, folder_id: ["ud_a"] if folder_id == "f1" else [])
    assert kf.collect_subtree_doc_ids("tenant1", "f1") == ["ud_a"]


def test_compute_subtree_doc_counts_nested():
    folders = [
        {
            "folder_id": "f_root",
            "parent_folder_id": None,
            "resource_counts": {"doc": 0},
        },
        {
            "folder_id": "f_child",
            "parent_folder_id": "f_root",
            "resource_counts": {"doc": 2},
        },
    ]
    counts = kf.compute_subtree_doc_counts(folders)
    assert counts["f_root"] == 2
    assert counts["f_child"] == 2


def test_compute_subtree_doc_counts_empty_subfolder_only():
    folders = [
        {"folder_id": "f_root", "parent_folder_id": None, "resource_counts": {"doc": 0}},
        {"folder_id": "f_child", "parent_folder_id": "f_root", "resource_counts": {"doc": 0}},
    ]
    counts = kf.compute_subtree_doc_counts(folders)
    assert counts["f_root"] == 0
    assert counts["f_child"] == 0
