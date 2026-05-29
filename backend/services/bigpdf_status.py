"""大 PDF 任务 UI 状态：区分「真排队」与「正在 Docling 解析」。"""

from __future__ import annotations

from typing import Any


def _norm_status(status: str | None) -> str:
    s = str(status or "queued").strip().lower()
    return "completed" if s == "done" else s


def _norm_stage(stage: str | None) -> str:
    return str(stage or "queued").strip().lower()


def bigpdf_display_stage(task: dict[str, Any]) -> str:
    """Map DB status/stage to frontend-friendly stage."""
    status = _norm_status(task.get("status"))
    stage = _norm_stage(task.get("stage"))
    if status in {"completed", "failed", "cancelled", "force_cancelled", "user_abandoned"}:
        return "completed" if status == "completed" else stage
    if status == "running" or task.get("docling_task_id") or task.get("worker_id"):
        if stage in {"queued", "running", ""}:
            return "parsing"
    if stage == "running":
        return "parsing"
    if stage == "packaging":
        return "packaging"
    return stage or "queued"


def resolve_bigpdf_ui_state(
    task: dict[str, Any],
    *,
    running_task_id: str | None = None,
    queue_position: int | None = None,
) -> dict[str, Any]:
    """
    解析大 PDF 任务应对用户展示的状态。

    规则：
    - 全局同时只处理 1 个大 PDF（另一任务 running 时，本任务 queued = 真排队）
    - 若本任务即为 running_task，或 status=running / 有 docling_task_id / worker_id → 解析中
    - 无其他 running 且本任务仍 queued → 等待 worker 领取（短暂，仍显示排队但带说明）
    """
    task_id = str(task.get("task_id") or "")
    status = _norm_status(task.get("status"))
    display_stage = bigpdf_display_stage(task)

    if status in {"completed", "failed", "cancelled", "force_cancelled", "user_abandoned"}:
        labels = {
            "completed": "已完成",
            "failed": "失败",
            "cancelled": "已取消",
            "force_cancelled": "已强制终止",
            "user_abandoned": "已停止跟踪",
        }
        return {
            "display_stage": display_stage,
            "display_label": labels.get(status, status),
            "is_processing": False,
            "queue_position": None,
            "is_waiting_for_slot": False,
        }

    is_this_running = bool(running_task_id and running_task_id == task_id)
    is_processing = (
        is_this_running
        or status == "running"
        or bool(task.get("docling_task_id"))
        or bool(task.get("worker_id"))
        or display_stage in {"parsing", "packaging"}
    )

    if is_processing:
        label = "打包中" if display_stage == "packaging" else "解析中"
        if task.get("docling_task_id") and display_stage == "parsing":
            label = "解析中（Docling）"
        return {
            "display_stage": display_stage if display_stage != "queued" else "parsing",
            "display_label": label,
            "is_processing": True,
            "queue_position": None,
            "is_waiting_for_slot": False,
        }

    # genuinely queued
    waiting_for_slot = bool(running_task_id and running_task_id != task_id)
    if waiting_for_slot:
        pos = queue_position if queue_position is not None else None
        label = f"排队中（第 {pos} 位）" if pos else "排队中（等待前序任务）"
    else:
        label = "排队中（等待调度）"

    return {
        "display_stage": "queued",
        "display_label": label,
        "is_processing": False,
        "queue_position": queue_position,
        "is_waiting_for_slot": waiting_for_slot,
    }
