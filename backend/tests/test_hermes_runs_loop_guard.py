from backend.services.hermes_orientg_policy import tool_progress_looks_like_shell
from backend.services.hermes_runs_loop_guard import HermesRunsLoopGuard, runs_read_timeout_s


def test_tool_progress_detects_python_c_orientg_mcp():
    msg = (
        "cd /e/proj && .venv/Scripts/python.exe -c "
        '"from services import orientg_mcp_tools; orientg_mcp_tools.orientg_kb_ask(...)"'
    )
    assert tool_progress_looks_like_shell(msg)


def test_runs_read_timeout_full_tier_at_least_1200():
    assert runs_read_timeout_s(orientg_route="hermes_full", configured=300) >= 1200.0


def test_loop_guard_aborts_after_forbidden_blocks():
    g = HermesRunsLoopGuard(orientg_route="hermes_full", max_forbidden_blocks=3)
    g.on_forbidden_block()
    g.on_forbidden_block()
    assert not g.should_abort()[0]
    g.on_forbidden_block()
    abort, code, _msg = g.should_abort()
    assert abort
    assert code == "hermes_run_forbidden_loop"


def test_loop_guard_does_not_abort_long_planning_without_kb_ask():
    import time

    g = HermesRunsLoopGuard(orientg_route="hermes_full")
    g.max_planning_chars = 100
    g.max_planning_s = 0.0
    g.accumulated_len = 200
    g.kb_ask_calls = 0
    g.started = time.monotonic() - 1.0
    abort, code, _msg = g.should_abort()
    assert not abort
    assert code == ""


def test_loop_guard_aborts_excessive_kb_ask_without_report():
    g = HermesRunsLoopGuard(orientg_route="hermes_full")
    g.sync_stats({"hermes_orientg_kb_ask_calls": 4})
    abort, code, _msg = g.should_abort()
    assert abort
    assert code == "hermes_kb_ask_loop"
