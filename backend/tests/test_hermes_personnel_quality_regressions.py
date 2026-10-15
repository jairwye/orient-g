"""人员横比质量回归：慢链/变薄/挂流/元指令泄漏（TDD）。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx

PERSONNEL_QUERY = "对比分析YYCQ和可比公司A25年的人员结构"


def test_full_report_ready_aborts_after_grace_not_round1_cut():
    """深度档对照终稿锚点出现后宽限收束，避免空转挂流；非旧 360s round1 打断。"""
    from backend.services.hermes_runs_loop_guard import HermesRunsLoopGuard

    g = HermesRunsLoopGuard(
        orientg_route="hermes_full",
        full_report_ready_grace_s=0.05,
    )
    g.sync_stats({"hermes_orientg_kb_ask_calls": 2})
    table = (
        "### 人员结构对照\n| 职能 | 可比公司A | YYCQ |\n"
        "| 研发 | 1378 | 70 |\n| 销售 | 946 | 证据未覆盖 |\n"
        "| 运营 | 242 | 61 |\n### 对比分析\n"
        "结构差异明显，口径不同，职能重心不同。" * 8
    )
    g.on_stream_evt({"type": "delta", "content": table})
    assert g.has_report_anchor
    g.accumulated_len = max(g.accumulated_len, 400)
    abort, code, _msg = g.should_abort()
    assert not abort
    import time

    time.sleep(0.08)
    abort, code, _msg = g.should_abort()
    assert abort
    assert code == "hermes_full_report_ready"


def test_sanitize_strips_payload_meta_instructions_from_final():
    """终稿不得残留 output_contract / 展示须用 / 禁止把内部代称 等元指令。"""
    from backend.services.hermes_stream_sanitize import finalize_agent_reply

    raw = (
        "### 人员结构对照\n"
        "| 职能归属 | 可比公司A | YYCQ |\n"
        "| --- | --- | --- |\n"
        "| 研发 | 1378 人 | 70 人 |\n"
        "| 销售 | 946 人 | 证据未覆盖 |\n"
        "| 运营 | 242 人 | 61 人 |\n\n"
        "### 对比分析\n"
        "- 结构差异：年报专业构成 vs excel 职能分项。\n"
        "- 职能重心：可比公司A销售/运营规模更大。\n"
        "- 口径：缺项标证据未覆盖。\n\n"
        "### 口径说明\n"
        "可比公司A=年报节选；YYCQ=excel「1.1信息-人员」。"
        "展示须用用户问句公司名（可比公司A/YYCQ），禁止把内部代称当主表表头。\n"
        "禁止把 YYCQ/可比公司A 当主表表头对外输出。\n"
        "next_action=write_final_answer_now evidence_sufficient=true\n"
    )
    out = finalize_agent_reply(raw, user_query=PERSONNEL_QUERY, tier2_native=True)
    assert "人员结构对照" in out
    assert "1378" in out or "1,378" in out
    assert "展示须用" not in out
    assert "内部代称" not in out
    assert "禁止把 YYCQ" not in out and "禁止把YYCQ" not in out
    assert "next_action" not in out
    assert "evidence_sufficient" not in out


def test_sanitize_keeps_legitimate_yycq_caliber_sentence():
    """合法口径约束句不得被元指令剥离误删。"""
    from backend.services.hermes_stream_sanitize import strip_payload_meta_instructions

    body = (
        "### 口径说明\n"
        "禁止把 YYCQ 员工总数与年报混加；分项以 excel「1.1信息-人员」为准。\n"
    )
    out = strip_payload_meta_instructions(body)
    assert "禁止把 YYCQ 员工总数与年报混加" in out


def test_sanitize_keeps_process_draft_with_inline_evidence_flag():
    """实质过程稿行内夹带 evidence_sufficient= 时不得整行抹空。"""
    from backend.services.hermes_stream_sanitize import (
        finalize_agent_reply,
        strip_payload_meta_instructions,
    )

    process = (
        "首轮取证完成。可比公司A研发人员1378人，YYCQ70人。"
        "正在做核证补缺计划后撰写终稿。evidence_sufficient=false"
    )
    stripped = strip_payload_meta_instructions(process)
    assert "1378" in stripped and "取证" in stripped
    assert "evidence_sufficient" not in stripped
    final = finalize_agent_reply(process, user_query=PERSONNEL_QUERY, tier2_native=True)
    assert "1378" in final and "取证" in final


def test_qualified_caliber_sentence_not_thin_salvage():
    """含骨架同款口径句、中等篇幅多职能表的合格稿不得判 thin salvage。"""
    from backend.services.kb_ask_mcp_agent_native import is_personnel_thin_salvage_final

    draft = (
        "### 人员结构对照\n"
        "| 职能归属 | 可比公司A | YYCQ |\n"
        "| --- | --- | --- |\n"
        "| 研发 | 1378 人 | 70 人 |\n"
        "| 销售 | 946 人 | 证据未覆盖 |\n"
        "| 运营 | 242 人 | 61 人 |\n"
        "| 管理 | 36 人 | 33.15 |\n"
        "| 支持 | 115 人 | 45.85 |\n\n"
        "### 对比分析\n"
        "- 结构差异：可比公司A与YYCQ披露口径不同（年报专业构成 vs excel 职能分项），"
        "不可直接比员工总数。\n"
        "- 职能重心：可比公司A销售/运营绝对值更大，YYCQ 研发占比相对更高。\n"
        "- 口径提醒：年报专节与 excel 分项不可混加。\n\n"
        "### 口径说明\n"
        "可比公司A=年报节选；YYCQ=excel「1.1信息-人员」。缺项标证据未覆盖。\n"
    )
    # 填充到 500–800 字量级，模拟骨架扩写后的正常成稿
    while len(draft) < 520:
        draft += "两侧职能分项已并列，横比须尊重披露口径差异。\n"
    assert 500 <= len(draft) <= 800
    assert draft.count("\n") >= 16
    assert not is_personnel_thin_salvage_final(draft)


def test_personnel_skeleton_has_multi_role_rows_without_meta_leak():
    """参考表须含多行职能；元指令不得写入可抄上屏的骨架正文。"""
    from backend.services.kb_ask_mcp_agent_native import (
        build_agent_payload,
        build_personnel_draft_skeleton_from_payload,
    )

    excerpts = [
        {
            "entity": "可比公司A",
            "doc_id": "ud_a",
            "excerpt": "研发人员数量 1,378；销售人员 946人；运营人员 242人；行政人员 36人",
        },
        {
            "entity": "YYCQ",
            "doc_id": "ud_b",
            "excerpt": "1.1信息-人员 研发 70.00 运营 61.00 管理 33.15 支持 45.85",
        },
    ]
    payload = build_agent_payload(
        query=PERSONNEL_QUERY,
        excerpts=excerpts,
        citations=[{"doc_id": "ud_a"}, {"doc_id": "ud_b"}],
    )
    sk = build_personnel_draft_skeleton_from_payload(payload)
    assert "人员结构对照" in sk
    assert sk.count("|") >= 10
    assert "研发" in sk and "销售" in sk and "运营" in sk
    assert "管理" in sk or "支持" in sk
    assert "对比分析" in sk
    assert sk.count("- ") >= 3
    assert "展示须用" not in sk
    assert "内部代称" not in sk
    assert "禁止把" not in sk


def test_write_final_body_encourages_full_chinese_report():
    from backend.services.hermes_kb_mcp_bridge import build_mcp_write_final_runs_body

    body = build_mcp_write_final_runs_body(
        user_query=PERSONNEL_QUERY,
        session_key="sk-wf-quality",
        model="hermes-agent",
    )
    instr = str(body.get("instructions") or "")
    assert "完整" in instr or "不少于" in instr
    assert "人员结构对照" in instr
    assert "对比分析" in instr
    assert "口径说明" in instr
    assert "元指令" in instr or "内部代称" in instr or "output_contract" in instr


@patch("backend.services.hermes_client.create_hermes_run")
@patch("backend.services.hermes_client.stop_hermes_run")
@patch("backend.services.hermes_client.settings")
def test_no_forced_round1_cut_while_composing_table(
    mock_settings,
    _mock_stop,
    mock_create_run,
):
    """主 run 已在写对照表时，不得因 360s 人员特判打断再串核证+成稿。"""
    mock_settings.hermes_configured = True
    mock_settings.hermes_model = "hermes-agent"
    mock_settings.hermes_request_timeout_s = 300
    mock_settings.hermes_stream_reasoning = False
    mock_settings.hermes_native_mcp_reply = True
    mock_create_run.side_effect = ["run_first"]

    table = (
        "### 人员结构对照\\n| 职能 | 可比公司A | YYCQ |\\n"
        "| 研发 | 1378 | 70 |\\n| 销售 | 946 | 证据未覆盖 |\\n"
        "| 运营 | 242 | 61 |\\n### 对比分析\\n结构差异明显，口径不同。"
        "### 口径说明\\n年报 vs excel。"
    )
    runs_sse = {
        "run_first": [
            'data: {"event":"tool.started","tool":"mcp__orientg__orientg_kb_ask","preview":"kb","run_id":"run_first"}',
            'data: {"event":"tool.completed","tool":"mcp__orientg__orientg_kb_ask","preview":"ok","run_id":"run_first"}',
            f'data: {{"event":"message.delta","delta":"{table}","run_id":"run_first"}}',
            f'data: {{"event":"run.completed","output":"{table}","run_id":"run_first"}}',
        ],
    }

    class _FakeResp:
        def __init__(self, lines):
            self.status_code = 200
            self._lines = lines

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def iter_lines(self):
            yield from self._lines

    def _stream_side_effect(method, url, **kwargs):
        rid = url.rsplit("/", 2)[-2] if "/events" in url else ""
        ctx = MagicMock()
        ctx.__enter__.return_value = _FakeResp(runs_sse.get(rid, []))
        return ctx

    fake_client = MagicMock()
    fake_client.stream.side_effect = _stream_side_effect
    fake_client.__enter__.return_value = fake_client
    fake_client.__exit__.return_value = False

    # 模拟已跑超过 360s：旧逻辑会 personnel_native_kb_round1_done
    t0 = 1_000_000.0
    ticks = {"n": 0}

    def _mono():
        ticks["n"] += 1
        # 首轮 loop 即视为已过 400s
        return t0 + 400.0 + ticks["n"] * 0.01

    with patch("backend.services.hermes_client.httpx.Client", return_value=fake_client):
        with patch(
            "backend.services.hermes_client._register_session",
            return_value="sk-no-cut",
        ):
            with patch("backend.services.hermes_client.time.monotonic", side_effect=_mono):
                events = list(
                    __import__(
                        "backend.services.hermes_client",
                        fromlist=["stream_agent_chat_runs"],
                    ).stream_agent_chat_runs(
                        messages=[{"role": "user", "content": PERSONNEL_QUERY}],
                        username="finance_test",
                        user_token="tok",
                        kb_scope={"selected_folder_ids": ["f1"]},
                        orientg_route="hermes_full",
                    )
                )

    steps = [str(e.get("step") or "") for e in events if e.get("type") == "status"]
    assert "personnel_mcp_round1_cut" not in steps
    assert "hermes_mcp_verify_continue" not in steps
    assert mock_create_run.call_count == 1
    done = next((e for e in events if e.get("type") == "done"), None)
    assert done is not None
    assert "人员结构对照" in str(done.get("reply") or "")


@patch("backend.services.hermes_client.create_hermes_run")
@patch("backend.services.hermes_client.stop_hermes_run")
@patch("backend.services.hermes_client.settings")
def test_write_final_followup_timeout_salvages_and_heartbeats(
    mock_settings,
    _mock_stop,
    mock_create_run,
):
    """成稿续跑挂流时须心跳保活，并 salvage 已有进展交付 done（不得空失败）。"""
    mock_settings.hermes_configured = True
    mock_settings.hermes_model = "hermes-agent"
    mock_settings.hermes_request_timeout_s = 300
    mock_settings.hermes_stream_reasoning = False
    mock_settings.hermes_native_mcp_reply = True
    mock_create_run.side_effect = ["run_first", "run_write_final"]

    process = (
        "首轮取证完成。可比公司A研发1378人 YYCQ研发70人。"
        "evidence_sufficient=false 核证补缺计划 next_action=verify_gap_then_write_final"
    )
    runs_sse = {
        "run_first": [
            'data: {"event":"tool.started","tool":"mcp__orientg__orientg_kb_ask","preview":"kb","run_id":"run_first"}',
            'data: {"event":"tool.completed","tool":"mcp__orientg__orientg_kb_ask","preview":"ok","run_id":"run_first"}',
            'data: {"event":"tool.started","tool":"mcp__orientg__orientg_kb_ask","preview":"kb2","run_id":"run_first"}',
            'data: {"event":"tool.completed","tool":"mcp__orientg__orientg_kb_ask","preview":"ok2","run_id":"run_first"}',
            f'data: {{"event":"message.delta","delta":"{process}","run_id":"run_first"}}',
            f'data: {{"event":"run.completed","output":"{process}","run_id":"run_first"}}',
        ],
        "run_write_final": [],
    }

    class _FakeResp:
        def __init__(self, lines, *, fail: bool = False):
            self.status_code = 200
            self._lines = lines
            self._fail = fail

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def iter_lines(self):
            if self._fail:
                raise httpx.TimeoutException("write_final hung")
            yield from self._lines

    def _stream_side_effect(method, url, **kwargs):
        rid = url.rsplit("/", 2)[-2] if "/events" in url else ""
        fail = rid == "run_write_final"
        ctx = MagicMock()
        ctx.__enter__.return_value = _FakeResp(runs_sse.get(rid, []), fail=fail)
        return ctx

    fake_client = MagicMock()
    fake_client.stream.side_effect = _stream_side_effect
    fake_client.__enter__.return_value = fake_client
    fake_client.__exit__.return_value = False

    with patch("backend.services.hermes_client.httpx.Client", return_value=fake_client):
        with patch(
            "backend.services.hermes_client._register_session",
            return_value="sk-wf-salvage",
        ):
            events = list(
                __import__(
                    "backend.services.hermes_client",
                    fromlist=["stream_agent_chat_runs"],
                ).stream_agent_chat_runs(
                    messages=[{"role": "user", "content": PERSONNEL_QUERY}],
                    username="finance_test",
                    user_token="tok",
                    kb_scope={"selected_folder_ids": ["f1"]},
                    orientg_route="hermes_full",
                    heartbeat_s=0.01,
                )
            )

    steps = [str(e.get("step") or "") for e in events if e.get("type") == "status"]
    assert "hermes_mcp_write_final_continue" in steps
    assert any(
        e.get("type") == "status" and e.get("step") == "hermes_followup_salvage"
        for e in events
    ), "成稿续跑超时须 salvage，不得空失败"
    done = next((e for e in events if e.get("type") == "done"), None)
    assert done is not None
    reply = str(done.get("reply") or "")
    assert "1378" in reply or "70" in reply or "取证" in reply
    assert done.get("type") == "done"


@patch("backend.services.hermes_client.create_hermes_run")
@patch("backend.services.hermes_client.stop_hermes_run")
@patch("backend.services.hermes_client.settings")
def test_kb1_with_user_facing_skips_verify_chain(
    mock_settings,
    _mock_stop,
    mock_create_run,
):
    """kb=1 但已有合格对照终稿 → 不得再核证/成稿连环。"""
    mock_settings.hermes_configured = True
    mock_settings.hermes_model = "hermes-agent"
    mock_settings.hermes_request_timeout_s = 300
    mock_settings.hermes_stream_reasoning = False
    mock_settings.hermes_native_mcp_reply = True
    mock_create_run.side_effect = ["run_first"]

    final = (
        "### 人员结构对照\\n| 职能 | 可比公司A | YYCQ |\\n"
        "| 研发 | 1378 | 70 |\\n| 销售 | 946 | 证据未覆盖 |\\n"
        "| 运营 | 242 | 61 |\\n### 对比分析\\n"
        "- 结构差异\\n- 职能重心\\n- 口径不同\\n### 口径说明\\n年报 vs excel"
    )
    runs_sse = {
        "run_first": [
            'data: {"event":"tool.started","tool":"mcp__orientg__orientg_kb_ask","preview":"kb","run_id":"run_first"}',
            'data: {"event":"tool.completed","tool":"mcp__orientg__orientg_kb_ask","preview":"ok","run_id":"run_first"}',
            f'data: {{"event":"message.delta","delta":"{final}","run_id":"run_first"}}',
            f'data: {{"event":"run.completed","output":"{final}","run_id":"run_first"}}',
        ],
    }

    class _FakeResp:
        def __init__(self, lines):
            self.status_code = 200
            self._lines = lines

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def iter_lines(self):
            yield from self._lines

    def _stream_side_effect(method, url, **kwargs):
        rid = url.rsplit("/", 2)[-2] if "/events" in url else ""
        ctx = MagicMock()
        ctx.__enter__.return_value = _FakeResp(runs_sse.get(rid, []))
        return ctx

    fake_client = MagicMock()
    fake_client.stream.side_effect = _stream_side_effect
    fake_client.__enter__.return_value = fake_client
    fake_client.__exit__.return_value = False

    with patch("backend.services.hermes_client.httpx.Client", return_value=fake_client):
        with patch(
            "backend.services.hermes_client._register_session",
            return_value="sk-skip-verify",
        ):
            events = list(
                __import__(
                    "backend.services.hermes_client",
                    fromlist=["stream_agent_chat_runs"],
                ).stream_agent_chat_runs(
                    messages=[{"role": "user", "content": PERSONNEL_QUERY}],
                    username="finance_test",
                    user_token="tok",
                    kb_scope={"selected_folder_ids": ["f1"]},
                    orientg_route="hermes_full",
                )
            )

    assert mock_create_run.call_count == 1
    gate = [
        str(e.get("message") or "")
        for e in events
        if e.get("type") == "status" and e.get("step") == "hermes_mcp_verify_gate"
    ]
    assert gate and "want=False" in gate[0]
    steps = [str(e.get("step") or "") for e in events if e.get("type") == "status"]
    assert "hermes_mcp_verify_continue" not in steps
    assert "hermes_mcp_write_final_continue" not in steps
