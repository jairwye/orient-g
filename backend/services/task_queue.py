"""
任务队列与优先级（在线问答 > 后台处理）、简单观测。
新增持久化调度：文档解析与 bigpdf 走 DB 租约队列，避免重启丢任务。
"""
import queue
import threading
import time
import uuid
from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Callable

from backend.config import settings
from backend.services import kb_tasks
from backend.services.ollama_guard import get_ollama_guard_state


class Priority(IntEnum):
    HIGH = 0
    LOW = 1


TASK_ONLINE_QA = "online_qa"
TASK_PDF_PARSE_DOCLING = "pdf_parse_docling"
TASK_KB_PACKAGE_GENERATE = "kb_package_generate"
TASK_KB_IMPORT_DELIVERY = "kb_import_delivery"
TASK_EMBED_AND_INDEX_REFRESH = "embed_and_index_refresh"

# 持久化任务 kind
TASK_KIND_USER_DOC_PARSE = "user_doc_parse"
TASK_KIND_BIGPDF_PARSE = "bigpdf"
PERSISTED_TASK_KINDS = {TASK_KIND_USER_DOC_PARSE, TASK_KIND_BIGPDF_PARSE}


@dataclass
class TaskItem:
    task_id: str | None
    task_type: str
    enqueued_at: float
    fn: Callable[..., Any]
    args: tuple[Any, ...]
    kwargs: dict[str, Any]


_stats_lock = threading.Lock()
_queue_high: queue.Queue = queue.Queue()
_queue_low: queue.Queue = queue.Queue()
_tasks_total = 0
_tasks_done = 0
_tasks_failed = 0
_tasks_total_by_type: dict[str, int] = {}
_tasks_done_by_type: dict[str, int] = {}
_tasks_failed_by_type: dict[str, int] = {}
_last_wait_seconds_high: float | None = None
_last_wait_seconds_low: float | None = None
_last_run_seconds: float | None = None
_running = False
_running_task_id: str | None = None
_running_task_type: str | None = None
_worker_thread: threading.Thread | None = None
_stop_event = threading.Event()
_poll_interval_s: float = 0.2
_worker_id = f"w_{uuid.uuid4().hex[:10]}"
_last_reap_at = 0.0


def _inc_total() -> None:
    global _tasks_total
    with _stats_lock:
        _tasks_total += 1


def _inc_done() -> None:
    global _tasks_done
    with _stats_lock:
        _tasks_done += 1


def _inc_failed() -> None:
    global _tasks_failed
    with _stats_lock:
        _tasks_failed += 1


def _inc_map(m: dict[str, int], k: str) -> None:
    kk = (k or "unknown").strip() or "unknown"
    m[kk] = int(m.get(kk, 0)) + 1


def _mark_running(task_id: str | None, task_type: str, *, wait_seconds: float | None = None, priority: Priority | None = None) -> None:
    global _running, _running_task_id, _running_task_type, _last_wait_seconds_high, _last_wait_seconds_low
    with _stats_lock:
        _running = True
        _running_task_id = task_id
        _running_task_type = task_type
        if wait_seconds is not None:
            if priority == Priority.HIGH:
                _last_wait_seconds_high = wait_seconds
            elif priority == Priority.LOW:
                _last_wait_seconds_low = wait_seconds


def _mark_done_run(t0: float | None) -> None:
    global _running, _running_task_id, _running_task_type, _last_run_seconds
    with _stats_lock:
        _last_run_seconds = max(0.0, time.time() - t0) if t0 is not None else None
        _running = False
        _running_task_id = None
        _running_task_type = None


def enqueue_user_doc_task(tenant_id: str, owner_username: str, doc_id: str) -> tuple[bool, str | None]:
    if not kb_tasks.supports_persisted_queue():
        from backend.services import kb_documents

        ok = submit(
            Priority.LOW,
            kb_documents.process_uploaded_document_task,
            tenant_id,
            doc_id,
            task_id=f"udoc_{doc_id}",
            task_type=TASK_PDF_PARSE_DOCLING,
        )
        return ok, (f"udoc_{doc_id}" if ok else None)
    qsz = kb_tasks.count_queue(priority=kb_tasks.QUEUE_PRIORITY_LOW)
    if qsz >= max(1, int(settings.queue_max_size_low)):
        return False, None
    task_id = f"udoc_{doc_id}"
    tid = kb_tasks.enqueue_task(
        tenant_id,
        owner_username,
        kind=TASK_KIND_USER_DOC_PARSE,
        task_id=task_id,
        detail=doc_id,
        payload={"doc_id": str(doc_id)},
        priority=kb_tasks.QUEUE_PRIORITY_LOW,
        dedupe_key=f"{tenant_id}:doc:{doc_id}",
    )
    return True, tid


def enqueue_bigpdf_task(tenant_id: str, owner_username: str, task_id: str) -> bool:
    if not kb_tasks.supports_persisted_queue():
        from backend.services.bigpdf_tasks import process_bigpdf_task

        return submit(
            Priority.HIGH,  # bigpdf 高优先级，优先于 user_doc_parse
            process_bigpdf_task,
            tenant_id,
            task_id,
            owner_username,
            task_id=task_id,
            task_type=TASK_PDF_PARSE_DOCLING,
        )
    # bigpdf 使用 HIGH 优先级，确保在 user_doc_parse 之前被处理
    qsz = kb_tasks.count_queue(priority=kb_tasks.QUEUE_PRIORITY_HIGH)
    if qsz >= max(1, int(settings.queue_max_size_high)):
        return False
    kb_tasks.update_task(
        tenant_id,
        task_id,
        status="queued",
        stage="queued",
        progress=0,
        payload={"task_id": str(task_id), "owner_username": str(owner_username)},
        priority=kb_tasks.QUEUE_PRIORITY_HIGH,
    )
    return True


def get_stats() -> dict:
    supports_persisted = kb_tasks.supports_persisted_queue()
    persisted_low = kb_tasks.count_queue(priority=kb_tasks.QUEUE_PRIORITY_LOW) if supports_persisted else 0
    persisted_overview = kb_tasks.queue_overview() if supports_persisted else {"queued": 0, "running": 0, "done": 0, "failed": 0}
    with _stats_lock:
        return {
            "queue_size_high": _queue_high.qsize(),
            "queue_size_low": _queue_low.qsize(),
            "queue_size_low_persisted": persisted_low,
            "persisted_tasks": persisted_overview,
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
            "queue_worker_id": _worker_id,
            "queue_persisted_enabled": supports_persisted,
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


def _run_next_memory() -> bool:
    for pri, q in ((Priority.HIGH, _queue_high), (Priority.LOW, _queue_low)):
        try:
            item: TaskItem = q.get_nowait()
        except queue.Empty:
            continue
        t0: float | None = None
        try:
            wait_s = max(0.0, time.time() - float(item.enqueued_at or time.time()))
            _mark_running(item.task_id, item.task_type, wait_seconds=wait_s, priority=pri)
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
            _mark_done_run(t0)
        return True
    return False


def _dispatch_persisted_task(task: dict[str, Any], is_cancelled=None) -> None:
    kind = str(task.get("kind") or "")
    tenant_id = str(task.get("tenant_id") or "")
    task_id = str(task.get("task_id") or "")
    owner = str(task.get("owner_username") or "")
    payload = task.get("payload") or {}
    if kind == TASK_KIND_USER_DOC_PARSE:
        from backend.services import kb_documents

        doc_id = str(payload.get("doc_id") or "")
        if not doc_id:
            raise RuntimeError("missing doc_id in payload")
        kb_documents.process_uploaded_document_task(tenant_id, doc_id, is_cancelled=is_cancelled)
        return
    if kind == TASK_KIND_BIGPDF_PARSE:
        from backend.services.bigpdf_tasks import process_bigpdf_task

        process_bigpdf_task(tenant_id, task_id, owner, is_cancelled=is_cancelled)
        return
    raise RuntimeError(f"unsupported persisted task kind: {kind}")


def _run_next_persisted() -> bool:
    if not kb_tasks.supports_persisted_queue():
        return False
    task = kb_tasks.claim_next_task(
        worker_id=_worker_id,
        lease_seconds=int(settings.queue_worker_lease_seconds),
        accepted_kinds=sorted(PERSISTED_TASK_KINDS),
    )
    if not task:
        return False
    task_id = str(task.get("task_id") or "")
    task_type = str(task.get("kind") or "")
    tenant_id = str(task.get("tenant_id") or "")
    t0 = time.time()
    _mark_running(task_id, task_type)
    hb_stop = threading.Event()

    def _hb() -> None:
        while not hb_stop.wait(timeout=max(3, int(settings.queue_worker_heartbeat_seconds))):
            try:
                # Check if task was cancelled; if so, signal main thread to stop
                if kb_tasks.is_task_cancelled(tenant_id, task_id):
                    hb_stop.set()
                    return
                kb_tasks.heartbeat_task(
                    tenant_id,
                    task_id,
                    worker_id=_worker_id,
                    lease_seconds=int(settings.queue_worker_lease_seconds),
                )
            except Exception:
                pass

    hb = threading.Thread(target=_hb, daemon=True, name=f"task-hb-{task_id[:8]}")
    hb.start()
    try:
        # Skip if task was cancelled before we started
        if kb_tasks.is_task_cancelled(tenant_id, task_id):
            kb_tasks.finish_task(
                tenant_id,
                task_id,
                worker_id=_worker_id,
                status="cancelled",
                stage="cancelled",
                progress=0,
                detail="cancelled before processing started",
            )
            return True
        _dispatch_persisted_task(task, is_cancelled=lambda: kb_tasks.is_task_cancelled(tenant_id, task_id))
        kb_tasks.finish_task(
            tenant_id,
            task_id,
            worker_id=_worker_id,
            status="done",
            stage="done",
            progress=100,
            detail=None,
        )
        _inc_done()
        with _stats_lock:
            _inc_map(_tasks_done_by_type, task_type)
    except Exception as e:
        bo = max(1, int(settings.queue_retry_backoff_seconds))
        bo = bo * max(1, int(task.get("attempts") or 1))
        bo = min(max(1, int(getattr(settings, "queue_retry_backoff_max_seconds", 900))), max(1, int(bo)))
        action = kb_tasks.fail_or_retry_task(
            tenant_id,
            task_id,
            worker_id=_worker_id,
            error=str(e),
            backoff_seconds=bo,
        )
        if task_type == TASK_KIND_USER_DOC_PARSE:
            from backend.services import kb_documents

            payload = task.get("payload") or {}
            doc_id = str(payload.get("doc_id") or "")
            if doc_id:
                if action == "retry":
                    kb_documents.mark_document_status(tenant_id, doc_id, "queued", f"任务重试中：{str(e)[:240]}")
                else:
                    kb_documents.mark_document_failed(tenant_id, doc_id, str(e))
        _inc_failed()
        with _stats_lock:
            _inc_map(_tasks_failed_by_type, task_type)
    finally:
        hb_stop.set()
        _mark_done_run(t0)
    return True


def _maybe_reap_stale_tasks() -> None:
    if not kb_tasks.supports_persisted_queue():
        return
    global _last_reap_at
    now = time.time()
    if (now - _last_reap_at) < max(10.0, float(settings.queue_worker_heartbeat_seconds)):
        return
    _last_reap_at = now
    kb_tasks.requeue_stale_tasks(
        running_timeout_seconds=int(settings.queue_running_timeout_seconds),
        queued_timeout_seconds=int(settings.queue_queued_timeout_seconds),
    )
    from backend.services import kb_documents

    for t in kb_tasks.list_failed_tasks(TASK_KIND_USER_DOC_PARSE, limit=120):
        tenant_id = str(t.get("tenant_id") or "")
        payload = t.get("payload") or {}
        doc_id = str(payload.get("doc_id") or "")
        if not tenant_id or not doc_id:
            continue
        kb_documents.mark_document_status(
            tenant_id,
            doc_id,
            "failed",
            str(t.get("last_error") or t.get("detail") or "任务失败"),
        )


def run_next() -> bool:
    _maybe_reap_stale_tasks()
    if _run_next_persisted():
        return True
    return _run_next_memory()


def start_worker(poll_interval_s: float = 0.2) -> None:
    global _worker_thread
    if _worker_thread and _worker_thread.is_alive():
        return
    _stop_event.clear()
    global _poll_interval_s
    _poll_interval_s = float(poll_interval_s or 0.2)

    def _loop() -> None:
        idle_min_s = max(0.0, float(getattr(settings, "queue_worker_idle_min_s", _poll_interval_s) or 0.0))
        idle_max_s = max(idle_min_s, float(getattr(settings, "queue_worker_idle_max_s", 5.0) or 5.0))
        idle_backoff = bool(getattr(settings, "queue_worker_idle_backoff", True))
        idle_sleep_s = idle_min_s
        while not _stop_event.is_set():
            try:
                did = run_next()
            except Exception:
                did = False
            if did:
                idle_sleep_s = idle_min_s
                continue
            if not idle_backoff:
                time.sleep(idle_min_s)
                continue
            time.sleep(idle_sleep_s)
            idle_sleep_s = min(idle_max_s, max(idle_min_s, idle_sleep_s * 2.0))

    _worker_thread = threading.Thread(target=_loop, name="task-queue-worker", daemon=True)
    _worker_thread.start()


def stop_worker() -> None:
    _stop_event.set()
