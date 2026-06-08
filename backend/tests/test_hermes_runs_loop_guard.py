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
