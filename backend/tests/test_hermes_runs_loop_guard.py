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


def test_loop_guard_forbidden_with_mcp_evidence_asks_write_final():
    """已有 MCP 取证时，execute_code 空转应收束为「写终稿」而非硬 abort→门禁顶替。"""
    g = HermesRunsLoopGuard(orientg_route="hermes_full", max_forbidden_blocks=3)
    g.sync_stats({"hermes_orientg_kb_ask_calls": 2})
    g.on_forbidden_block()
    g.on_forbidden_block()
    g.on_forbidden_block()
    abort, code, msg = g.should_abort()
    assert abort
    assert code == "hermes_forbidden_write_final"
    assert "成稿" in msg or "终稿" in msg
    assert "execute_code" in msg or "MCP" in msg


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
    g.sync_stats({"hermes_orientg_kb_ask_calls": 5})
    assert not g.should_abort()[0]
    g.sync_stats({"hermes_orientg_kb_ask_calls": 6})
    abort, code, _msg = g.should_abort()
    assert abort
    assert code == "hermes_kb_ask_loop"


def test_lite_loop_guard_aborts_after_personnel_report_ready_grace():
    """标准档：对照表已齐后勿空转续写；收束让 Orient-G finalize/done（勿伤深度档）。"""
    import time

    g = HermesRunsLoopGuard(orientg_route="hermes_lite")
    g.on_stream_evt(
        {
            "type": "delta",
            "content": (
                "## 人员结构对照\n| 职能 | 可比公司A | YYCQ |\n"
                "| 研发 | 1378 | 70 |\n| 销售 | 946 | — |\n| 运营 | 242 | 61 |\n"
            ),
        }
    )
    assert g.has_report_anchor
    assert g.report_ready_at is not None
    g.report_ready_at = time.monotonic() - 95.0
    g.accumulated_len = 800
    abort, code, _msg = g.should_abort()
    assert abort
    assert code == "personnel_lite_report_ready"


def test_full_loop_guard_aborts_permission_web_stall_cycles():
    """深度档：过程稿反复「权限受限」+ web/memory 空转须收束。"""
    g = HermesRunsLoopGuard(orientg_route="hermes_full", max_permission_web_stalls=3)
    stall = (
        "知识库当前权限受限，无法检索。接下来用 web_search 查公开数据，"
        "若失败再加载 web-tools skill。"
    )
    for _ in range(3):
        g.on_stream_evt({"type": "delta", "content": stall})
    abort, code, _msg = g.should_abort()
    assert abort
    assert code == "hermes_permission_web_stall"


def test_full_loop_guard_skips_permission_web_stall_when_report_anchor():
    g = HermesRunsLoopGuard(orientg_route="hermes_full", max_permission_web_stalls=2)
    g.on_stream_evt(
        {
            "type": "delta",
            "content": "## 人员结构对照\n| 职能 | 可比公司A | YYCQ |\n| 研发 | 1378 | 70 |\n",
        }
    )
    assert g.has_report_anchor
    stall = "知识库权限受限，无法检索；改用 memory 与 web-tools。"
    g.on_stream_evt({"type": "delta", "content": stall})
    g.on_stream_evt({"type": "delta", "content": stall})
    abort, code, _msg = g.should_abort()
    assert not abort
    assert code == ""


def test_full_loop_guard_does_not_abort_report_ready_without_kb():
    """深度档：仅有对照锚点但尚未 MCP 取证时，不得因 grace 收束（仍须取证）。"""
    import time

    g = HermesRunsLoopGuard(orientg_route="hermes_full")
    g.on_stream_evt(
        {
            "type": "delta",
            "content": "## 人员结构对照\n| 研发 | 1378 | 70 |\n| 销售 | 946 | — |\n",
        }
    )
    g.report_ready_at = time.monotonic() - 200.0
    g.accumulated_len = 2000
    g.kb_ask_calls = 0
    abort, code, _msg = g.should_abort()
    assert not abort
    assert code == ""


def test_full_loop_guard_aborts_after_report_ready_grace_with_kb():
    """深度档：已 MCP + 对照终稿锚点后宽限收束，避免空转挂流。"""
    import time

    g = HermesRunsLoopGuard(
        orientg_route="hermes_full",
        full_report_ready_grace_s=60.0,
    )
    g.sync_stats({"hermes_orientg_kb_ask_calls": 2})
    g.on_stream_evt(
        {
            "type": "delta",
            "content": "## 人员结构对照\n| 研发 | 1378 | 70 |\n| 销售 | 946 | — |\n",
        }
    )
    g.report_ready_at = time.monotonic() - 95.0
    g.accumulated_len = 2000
    abort, code, _msg = g.should_abort()
    assert abort
    assert code == "hermes_full_report_ready"


def test_full_loop_guard_ignores_tool_progress_skeleton_anchor():
    """MCP tool_progress 含骨架标题不得立锚点，避免未成稿就 grace 收束。"""
    g = HermesRunsLoopGuard(orientg_route="hermes_full", full_report_ready_grace_s=1.0)
    g.sync_stats({"hermes_orientg_kb_ask_calls": 2})
    g.on_stream_evt(
        {
            "type": "tool_progress",
            "message": "## 【硬数字参考表】\n### 人员结构对照\n| 研发 | 1378 | 70 |\n",
        }
    )
    assert not g.has_report_anchor
    abort, code, _msg = g.should_abort()
    assert not abort
