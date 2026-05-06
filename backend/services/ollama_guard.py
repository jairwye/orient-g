"""
2.e 落地：Ollama 调用的“资源信号量 + 熔断”护栏。

- gpu semaphore：限制本机推理/嵌入并发（避免显存/CPU 打满）
- circuit breaker：Ollama 不可用时快速失败一段时间，防止请求雪崩

说明：这是进程内实现，适用于单机部署；若后续引入多进程/多机，应迁移到分布式限流/熔断组件。
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any

import httpx

from backend.config import settings


class OllamaCircuitOpen(RuntimeError):
    pass


@dataclass
class CircuitState:
    consecutive_failures: int = 0
    open_until_ts: float = 0.0
    last_error: str | None = None


_circuit_lock = threading.Lock()
# Ollama（嵌入/可选旧对话）与远程 LLM（OpenAI 兼容）分开展示与熔断，避免一侧失败拖死另一侧
_circuit_ollama = CircuitState()
_circuit_llm = CircuitState()


def _now() -> float:
    return time.time()


def _circuit_bucket(circuit_scope: str) -> CircuitState:
    return _circuit_llm if circuit_scope == "llm" else _circuit_ollama


def _circuit_is_open(circuit_scope: str, now: float | None = None) -> bool:
    t = _now() if now is None else now
    with _circuit_lock:
        c = _circuit_bucket(circuit_scope)
        return bool(c.open_until_ts and t < c.open_until_ts)


def _circuit_note_success(circuit_scope: str) -> None:
    with _circuit_lock:
        c = _circuit_bucket(circuit_scope)
        c.consecutive_failures = 0
        c.open_until_ts = 0.0
        c.last_error = None


def _circuit_note_failure(circuit_scope: str, err: Exception) -> None:
    now = _now()
    with _circuit_lock:
        c = _circuit_bucket(circuit_scope)
        c.consecutive_failures += 1
        c.last_error = str(err) or repr(err)
        if c.consecutive_failures >= max(1, int(settings.ollama_circuit_fail_threshold)):
            open_s = max(1, int(settings.ollama_circuit_open_seconds))
            c.open_until_ts = max(c.open_until_ts, now + open_s)


def _circuit_snapshot(c: CircuitState, *, now: float) -> dict[str, Any]:
    open_until = float(c.open_until_ts or 0.0)
    return {
        "circuit_open": bool(open_until and now < open_until),
        "circuit_open_seconds_remaining": max(0.0, open_until - now) if open_until else 0.0,
        "circuit_consecutive_failures": int(c.consecutive_failures),
        "circuit_last_error": c.last_error,
    }


_gpu_sem = threading.Semaphore(max(1, int(settings.gpu_max_concurrency)))


def get_ollama_guard_state() -> dict[str, Any]:
    """给 /api/queue/stats 等观测端使用。"""
    now = _now()
    with _circuit_lock:
        o = _circuit_snapshot(_circuit_ollama, now=now)
        llm = _circuit_snapshot(_circuit_llm, now=now)
        out: dict[str, Any] = {
            **o,
            "gpu_max_concurrency": int(settings.gpu_max_concurrency),
            "llm_circuit_open": llm["circuit_open"],
            "llm_circuit_open_seconds_remaining": llm["circuit_open_seconds_remaining"],
            "llm_circuit_consecutive_failures": llm["circuit_consecutive_failures"],
            "llm_circuit_last_error": llm["circuit_last_error"],
        }
        out["llm_guard"] = llm
        return out


def post_json_with_guard(
    *,
    url: str,
    payload: dict[str, Any],
    timeout_s: float,
    kind: str,
    headers: dict[str, str] | None = None,
    circuit_scope: str = "ollama",
) -> dict[str, Any]:
    """
    统一封装 Ollama POST 调用：
    - 熔断打开时快速失败
    - 获取 GPU 信号量（超时则失败）
    - 调用成功：复位熔断
    - 调用失败：累计失败并可能打开熔断
    """
    label = "LLM" if circuit_scope == "llm" else "Ollama"
    if _circuit_is_open(circuit_scope):
        raise OllamaCircuitOpen(f"{label} 熔断已打开（{kind}），请稍后重试")

    acquired = _gpu_sem.acquire(timeout=max(0.1, float(settings.gpu_acquire_timeout_s)))
    if not acquired:
        raise TimeoutError("推理资源繁忙（GPU semaphore acquire timeout），请稍后重试")
    try:
        with httpx.Client(timeout=timeout_s) as client:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        if not isinstance(data, dict):
            raise RuntimeError(f"{label} 响应不是 JSON 对象")
        _circuit_note_success(circuit_scope)
        return data
    except Exception as e:
        _circuit_note_failure(circuit_scope, e)
        raise
    finally:
        try:
            _gpu_sem.release()
        except Exception:
            pass

