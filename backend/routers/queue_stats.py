"""
任务队列观测：暴露队列长度与任务计数，供监控/告警使用。
"""
from fastapi import APIRouter

from backend.services.task_queue import get_stats

router = APIRouter()


@router.get("/stats")
def queue_stats():
    """返回当前队列与任务统计。"""
    return get_stats()
