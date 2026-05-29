"""TDD: 大 PDF UI 状态 — 真排队 vs 正在解析。"""

from backend.services.bigpdf_status import bigpdf_display_stage, resolve_bigpdf_ui_state


def test_display_stage_running_means_parsing():
    assert bigpdf_display_stage({"status": "running", "stage": "running"}) == "parsing"
    assert bigpdf_display_stage({"status": "queued", "stage": "queued", "docling_task_id": "d1"}) == "parsing"


def test_only_one_bigpdf_when_other_running_show_queue():
    """另一任务在跑时，本任务 queued 是真排队。"""
    ui = resolve_bigpdf_ui_state(
        {"task_id": "t_new", "status": "queued", "stage": "queued"},
        running_task_id="t_old",
        queue_position=1,
    )
    assert ui["is_processing"] is False
    assert ui["is_waiting_for_slot"] is True
    assert ui["display_stage"] == "queued"
    assert "排队中" in ui["display_label"]
    assert "1" in ui["display_label"]


def test_current_task_is_running_show_parsing_not_queue():
    """本任务正在跑（running_task 指向自己）时必须显示解析中，不能显示排队中。"""
    ui = resolve_bigpdf_ui_state(
        {"task_id": "t_mine", "status": "running", "stage": "parsing", "progress": 30},
        running_task_id="t_mine",
    )
    assert ui["is_processing"] is True
    assert ui["display_label"] == "解析中"
    assert ui["display_stage"] == "parsing"


def test_docling_submitted_while_db_still_queued_shows_parsing():
    """已提交 Docling 但 DB stage 仍为 queued 时，应对用户显示解析中。"""
    ui = resolve_bigpdf_ui_state(
        {"task_id": "t1", "status": "running", "stage": "queued", "docling_task_id": "dl_abc"},
        running_task_id="t1",
    )
    assert ui["is_processing"] is True
    assert ui["display_stage"] == "parsing"
    assert "Docling" in ui["display_label"]


def test_sole_queued_no_runner_is_waiting_dispatch():
    """队列中唯一任务、尚无 running → 等待 worker 领取（短暂状态）。"""
    ui = resolve_bigpdf_ui_state(
        {"task_id": "t_only", "status": "queued", "stage": "queued"},
        running_task_id=None,
        queue_position=None,
    )
    assert ui["is_processing"] is False
    assert ui["is_waiting_for_slot"] is False
    assert "等待调度" in ui["display_label"]
