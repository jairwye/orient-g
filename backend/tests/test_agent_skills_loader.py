from backend.services import agent_skills_loader as asl


def test_registered_skill_ids_contains_data_parse():
    ids = asl.registered_skill_ids()
    assert "skill.data_parse.interpret.v1" in ids
    assert "skill.data_parse.playbook.v1" in ids
    assert "skill.data_parse.xlsx.v1" in ids
    assert "skill.project_accounting_table.v1" in ids


def test_load_skill_document_playbook():
    doc = asl.load_skill_document("skill.data_parse.playbook.v1")
    assert doc is not None
    assert doc["id"] == "skill.data_parse.playbook.v1"
    assert "Playbook" in (doc["body_markdown"] or "")
    assert "name:" in (doc["raw_markdown"] or "")


def test_build_system_addon_respects_enabled_list():
    addon = asl.build_system_addon_for_enabled_skills(
        ["skill.data_parse.playbook.v1", "skill.unknown.skill.v1"],
        max_total_chars=50000,
    )
    assert "skill.data_parse.playbook.v1" in addon
    assert "unknown" not in addon


def test_build_system_addon_truncation():
    addon = asl.build_system_addon_for_enabled_skills(
        ["skill.data_parse.interpret.v1"],
        max_total_chars=80,
    )
    assert "截断" in addon or len(addon) <= 80


def test_list_skill_documents():
    lst = asl.list_skill_documents()
    assert len(lst) >= 3
    ids = {x["id"] for x in lst}
    assert "skill.project_accounting_table.v1" in ids
