"""Orient-G run_id 与 Hermes run_id 绑定（取消时 stop）。"""

from __future__ import annotations

from backend.services.agent_run_registry import (
    bind_hermes_run,
    cancel,
    pop_hermes_run_id,
    register,
)


def test_bind_and_pop_hermes_run():
    register("og-1")
    bind_hermes_run("og-1", "run_xyz")
    assert pop_hermes_run_id("og-1") == "run_xyz"
    assert pop_hermes_run_id("og-1") is None


def test_cancel_clears_binding():
    register("og-2")
    bind_hermes_run("og-2", "run_abc")
    cancel("og-2")
    assert pop_hermes_run_id("og-2") is None
