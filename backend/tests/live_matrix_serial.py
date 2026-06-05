"""Live 财务矩阵：进程级串行锁 + 用例间隔（本地 LLM 仅 2 路，勿并行压测）。"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

_LOCK_PATH = Path(__file__).resolve().parent / "reports" / ".live_matrix.lock"
_DEFAULT_COOLDOWN_S = 5.0


def case_cooldown_seconds() -> float:
    raw = (os.environ.get("ORIENTG_LIVE_MATRIX_CASE_COOLDOWN_S") or "").strip()
    if not raw:
        return _DEFAULT_COOLDOWN_S
    try:
        return max(0.0, float(raw))
    except ValueError:
        return _DEFAULT_COOLDOWN_S


@pytest.fixture(scope="session", autouse=True)
def _live_matrix_process_lock():
    """
    同一时刻只允许一个 live 矩阵 pytest 进程（避免多 shell 并行占满 LLM）。
    若锁已存在则 skip 整个 session。
    """
    _LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    pid = os.getpid()
    if _LOCK_PATH.exists():
        try:
            holder = _LOCK_PATH.read_text(encoding="utf-8").strip()
        except OSError:
            holder = "?"
        pytest.skip(
            f"另一 live 矩阵任务进行中（lock={_LOCK_PATH.name} pid={holder}）；"
            "请等其结束或删除锁文件后再跑。"
        )
    try:
        _LOCK_PATH.write_text(str(pid), encoding="utf-8")
    except OSError as e:
        pytest.skip(f"无法创建 live 矩阵锁：{e}")
    yield
    try:
        if _LOCK_PATH.exists() and _LOCK_PATH.read_text(encoding="utf-8").strip() == str(pid):
            _LOCK_PATH.unlink(missing_ok=True)
    except OSError:
        pass


@pytest.fixture(autouse=True)
def _live_matrix_case_cooldown():
    """每条用例结束后冷却，给本地 LLM / GPU semaphore 释放时间。"""
    yield
    cd = case_cooldown_seconds()
    if cd > 0:
        time.sleep(cd)
