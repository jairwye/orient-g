from backend.routers import knowledge


def test_visible_name_conflict_includes_shared_folder(monkeypatch):
    def fake_list_folders(_tenant_id: str):
        return [
            {
                "folder_id": "f_shared_contract",
                "name": "合同台账",
                "owner_username": None,
                "collection_ids": ["c_dept_finance_public"],
            }
        ]

    monkeypatch.setattr(knowledge, "list_folders", fake_list_folders)
    ok = knowledge._is_visible_folder_name_conflict(
        tenant_id="tenant1",
        username="user_fin_1",
        allowed_col_ids={"c_dept_finance_public"},
        target_name="合同台账",
    )
    assert ok is True


def test_visible_name_conflict_excludes_self_when_renaming(monkeypatch):
    def fake_list_folders(_tenant_id: str):
        return [
            {
                "folder_id": "f_self",
                "name": "合同台账",
                "owner_username": "alice",
                "collection_ids": ["c_private_dyn_alice"],
            }
        ]

    monkeypatch.setattr(knowledge, "list_folders", fake_list_folders)
    ok = knowledge._is_visible_folder_name_conflict(
        tenant_id="tenant1",
        username="alice",
        allowed_col_ids={"c_private_dyn_alice"},
        target_name=" 合同台账 ",
        exclude_folder_id="f_self",
    )
    assert ok is False


def test_visible_name_conflict_detects_private_owner_folder(monkeypatch):
    def fake_list_folders(_tenant_id: str):
        return [
            {
                "folder_id": "f_private_u1",
                "name": "我的合同台账",
                "owner_username": "u1",
                "collection_ids": [],
            }
        ]

    monkeypatch.setattr(knowledge, "list_folders", fake_list_folders)
    ok = knowledge._is_visible_folder_name_conflict(
        tenant_id="tenant1",
        username="u1",
        allowed_col_ids=set(),
        target_name="我的合同台账",
    )
    assert ok is True
