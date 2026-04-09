"""
任务队列与优先级（在线问答 > 后台处理）、简单观测。
双队列、限并发与降级策略见 规划/task-queue-and-observability.md。
"""
import queue
import threading
import time
from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Callable

from backend.config import settings
from backend.services.ollama_guard import get_ollama_guard_state

# 优先级：高 = 在线问答，低 = 后台处理
class Priority(IntEnum):
    HIGH = 0
    LOW = 1


# 任务类型（用于指标与验收口径）
TASK_ONLINE_QA = "online_qa"
TASK_PDF_PARSE_DOCLING = "pdf_parse_docling"
TASK_KB_PACKAGE_GENERATE = "kb_package_generate"
TASK_KB_IMPORT_DELIVERY = "kb_import_delivery"
TASK_EMBED_AND_INDEX_REFRESH = "embed_and_index_refresh"


@dataclass
class TaskItem:
    task_id: str | None
    task_type: str
    enqueued_at: float
    fn: Callable[..., Any]
    args: tuple[Any, ...]
    kwargs: dict[str, Any]


# 进程内单例，供观测与后续任务接入使用
_stats_lock = threading.Lock()
_queue_high: queue.Queue = queue.Queue()
_queue_low: queue.Queue = queue.Queue()
_tasks_total = 0
_tasks_done = 0
_tasks_failed = 0
_tasks_total_by_type: dict[str, int] = {}
_tasks_done_by_type: dict[str, int] = {}
_tasks_failed_by_type: dict[str, int] = {}
# 最近一次等待/执行耗时（用于验收与基线）
_last_wait_seconds_high: float | None = None
_last_wait_seconds_low: float | None = None
_last_run_seconds: float | None = None
# running 状态（用于观测）
_running = False
_running_task_id: str | None = None
_running_task_type: str | None = None
# worker 控制
_worker_thread: threading.Thread | None = None
_stop_event = threading.Event()
_poll_interval_s: float = 0.2


def _inc_total():
    global _tasks_total
    with _stats_lock:
        _tasks_total += 1


def _inc_done():
    global _tasks_done
    with _stats_lock:
        _tasks_done += 1


def _inc_failed():
    global _tasks_failed
    with _stats_lock:
        _tasks_failed += 1


def _inc_map(m: dict[str, int], k: str) -> None:
    kk = (k or "unknown").strip() or "unknown"
    m[kk] = int(m.get(kk, 0)) + 1


def get_stats() -> dict:
    """返回当前队列与任务统计，供观测/告警使用。"""
    with _stats_lock:
        return {
            "queue_size_high": _queue_high.qsize(),
            "queue_size_low": _queue_low.qsize(),
            "tasks_total": _tasks_total,
            "tasks_done": _tasks_done,
            "tasks_failed": _tasks_failed,
            "tasks_total_by_type": dict(_tasks_total_by_type),
            "tasks_done_by_type": dict(_tasks_done_by_type),
            "tasks_failed_by_type": dict(_tasks_failed_by_type),
            "running": _running,
            "running_task_id": _running_task_id,
            "running_task_type": _running_task_type,
            "last_wait_seconds_high": _last_wait_seconds_high,
            "last_wait_seconds_low": _last_wait_seconds_low,
            "last_run_seconds": _last_run_seconds,
            "queue_max_size_high": int(settings.queue_max_size_high),
            "queue_max_size_low": int(settings.queue_max_size_low),
            "queue_degrade_high_threshold": int(settings.queue_degrade_high_threshold),
            "ollama_guard": get_ollama_guard_state(),
        }


def submit(
    priority: Priority,
    fn: Callable[..., Any],
    *args: Any,
    task_id: str | None = None,
    task_type: str = "unknown",
    **kwargs: Any,
) -> bool:
    """
    将任务放入对应优先级队列。
    返回 True 表示已接受入队，False 表示队列已满拒绝。
    """
    q = _queue_high if priority == Priority.HIGH else _queue_low
    max_sz = int(settings.queue_max_size_high if priority == Priority.HIGH else settings.queue_max_size_low)
    if q.qsize() >= max(1, max_sz):
        return False
    _inc_total()
    try:
        with _stats_lock:
            _inc_map(_tasks_total_by_type, task_type)
        q.put(
            TaskItem(
                task_id=task_id,
                task_type=(task_type or "unknown").strip() or "unknown",
                enqueued_at=time.time(),
                fn=fn,
                args=tuple(args),
                kwargs=dict(kwargs),
            )
        )
    except Exception:
        _inc_failed()
        with _stats_lock:
            _inc_map(_tasks_failed_by_type, task_type)
        return False
    return True


def run_next() -> bool:
    """
    按优先级执行下一个任务：先高后低。
    返回 True 表示执行了一个任务，False 表示两队列皆空。
    """
    for pri, q in ((Priority.HIGH, _queue_high), (Priority.LOW, _queue_low)):
        try:
            item: TaskItem = q.get_nowait()
            try:
                global _running, _running_task_id, _running_task_type, _last_wait_seconds_high, _last_wait_seconds_low, _last_run_seconds
                with _stats_lock:
                    _running = True
                    _running_task_id = item.task_id
                    _running_task_type = item.task_type
                    wait_s = max(0.0, time.time() - float(item.enqueued_at or time.time()))
                    if pri == Priority.HIGH:
                        _last_wait_seconds_high = wait_s
                    else:
                        _last_wait_seconds_low = wait_s
                t0 = time.time()
                item.fn(*item.args, **item.kwargs)
                _inc_done()
                with _stats_lock:
                    _inc_map(_tasks_done_by_type, item.task_type)
            except Exception:
                _inc_failed()
                with _stats_lock:
                    _inc_map(_tasks_failed_by_type, item.task_type)
            finally:
                with _stats_lock:
                    _last_run_seconds = max(0.0, time.time() - t0) if "t0" in locals() else None
                with _stats_lock:
                    _running = False
                    _running_task_id = None
                    _running_task_type = None
            return True
        except queue.Empty:
            continue
    return False


def start_worker(poll_interval_s: float = 0.2) -> None:
    """
    启动后台 worker 线程：循环执行 run_next。
    """
    global _worker_thread
    if _worker_thread and _worker_thread.is_alive():
        return
    _stop_event.clear()
    global _poll_interval_s
    _poll_interval_s = float(poll_interval_s or 0.2)

    def _loop():
        while not _stop_event.is_set():
            did = run_next()
            if not did:
                time.sleep(_poll_interval_s)

    _worker_thread = threading.Thread(target=_loop, name="task-queue-worker", daemon=True)
    _worker_thread.start()


def stop_worker() -> None:
    _stop_event.set()
