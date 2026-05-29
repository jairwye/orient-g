"""进行中的 Agent 流式任务注册表（用于用户点击「停止」）。"""

from __future__ import annotations

import threading
from typing import Any

_lock = threading.Lock()
_runs: dict[str, dict[str, Any]] = {}


def register(run_id: str) -> threading.Event:
    rid = (run_id or "").strip()
    if not rid:
        rid = f"run_{id(threading.current_thread())}"
    ev = threading.Event()
    with _lock:
        _runs[rid] = {"cancel": ev, "hermes_run_id": None}
    return ev


def bind_hermes_run(orientg_run_id: str, hermes_run_id: str) -> None:
    """绑定 Orient-G 流式 run_id 与 Hermes POST /v1/runs 返回的 run_id（用于 stop）。"""
    rid = (orientg_run_id or "").strip()
    hid = (hermes_run_id or "").strip()
    if not rid or not hid:
        return
    with _lock:
        entry = _runs.get(rid)
        if entry is not None:
            entry["hermes_run_id"] = hid


def pop_hermes_run_id(orientg_run_id: str) -> str | None:
    rid = (orientg_run_id or "").strip()
    with _lock:
        entry = _runs.get(rid)
        if not entry:
            return None
        hid = entry.pop("hermes_run_id", None)
    return str(hid).strip() if hid else None


def cancel(run_id: str) -> bool:
    rid = (run_id or "").strip()
    with _lock:
        entry = _runs.get(rid)
    if not entry:
        return False
    entry["cancel"].set()
    entry.pop("hermes_run_id", None)
    return True


def is_cancelled(run_id: str | None) -> bool:
    if not run_id:
        return False
    with _lock:
        entry = _runs.get(run_id.strip())
    return bool(entry and entry["cancel"].is_set())


def unregister(run_id: str | None) -> None:
    if not run_id:
        return
    with _lock:
        _runs.pop(run_id.strip(), None)
