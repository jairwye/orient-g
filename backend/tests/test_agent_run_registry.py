"""Agent 流式任务取消注册表。"""

from __future__ import annotations

from backend.services.agent_run_registry import cancel, is_cancelled, register, unregister


def test_register_cancel_unregister():
    ev = register("run_test_1")
    assert not ev.is_set()
    assert not is_cancelled("run_test_1")
    assert cancel("run_test_1")
    assert ev.is_set()
    assert is_cancelled("run_test_1")
    unregister("run_test_1")
    assert not is_cancelled("run_test_1")
    assert not cancel("run_test_1")


def test_cancel_unknown_run():
    assert not cancel("run_missing")
