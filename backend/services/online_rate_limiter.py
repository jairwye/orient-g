"""
2.e 落地：在线互动（按用户）限速。

实现：进程内 token bucket。
注意：单机/单进程可用；多进程需外置存储（Redis 等）才能一致。
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from backend.config import settings


@dataclass
class Bucket:
    tokens: float
    last_ts: float


_lock = threading.Lock()
_buckets: dict[str, Bucket] = {}


def _now() -> float:
    return time.time()


def allow(*, key: str, rps: float | None = None, burst: int | None = None) -> bool:
    """
    返回 True 表示允许通过，False 表示被限速。
    - rps: 平均每秒补充 token 数
    - burst: 最大桶容量（瞬时突发）
    """
    k = (key or "").strip() or "anonymous"
    rr = float(settings.online_user_rps if rps is None else rps)
    bb = int(settings.online_user_burst if burst is None else burst)
    rr = max(0.01, rr)
    bb = max(1, bb)
    now = _now()

    with _lock:
        b = _buckets.get(k)
        if b is None:
            b = Bucket(tokens=float(bb), last_ts=now)
            _buckets[k] = b
        # refill
        dt = max(0.0, now - float(b.last_ts))
        b.tokens = min(float(bb), float(b.tokens) + dt * rr)
        b.last_ts = now
        if b.tokens >= 1.0:
            b.tokens -= 1.0
            return True
        return False


def snapshot() -> dict:
    """给观测用：桶数量。避免暴露用户信息，仅返回聚合。"""
    with _lock:
        return {"bucket_count": len(_buckets)}

