"""Live：finance_test 深度档人员结构 + Hermes MCP 不得权限受限。"""

from __future__ import annotations

import json
import os
import re
import time

import pytest
from fastapi.testclient import TestClient

from backend.config import settings
from backend.main import app
from backend.routers.settings import DEPARTMENT_FINANCE
from backend.services.dev_users import ensure_department_test_user
from backend.tests.test_acl_folder_shared_docs import FOLDER_JINGPIN_CAIBAO_25

PERSONNEL_QUERY = "对比分析YYCQ和可比公司A25年的人员结构"

pytestmark = pytest.mark.skipif(
    os.environ.get("ORIENTG_LIVE_PERSONNEL_MCP") != "1",
    reason="set ORIENTG_LIVE_PERSONNEL_MCP=1",
)

client = TestClient(app)


def _token() -> str:
    ensure_department_test_user(
        "finance_test",
        password="FinanceTest!2026",
        department=DEPARTMENT_FINANCE,
    )
    r = client.post(
        "/api/auth/login",
        json={"username": "finance_test", "password": "FinanceTest!2026"},
    )
    assert r.status_code == 200
    return r.json()["token"]


def _parse_sse(text: str) -> list[dict]:
    out = []
    for block in text.split("\n\n"):
        for line in block.split("\n"):
            if line.strip().startswith("data:"):
                raw = line.strip()[5:].strip()
                if raw and raw != "[DONE]":
                    try:
                        out.append(json.loads(raw))
                    except json.JSONDecodeError:
                        pass
    return out


def test_deep_personnel_stream_not_permission_denied():
    if not settings.hermes_configured:
        pytest.skip("Hermes not configured")
    tok = _token()
    r = client.post(
        "/api/agent/chat/stream",
        headers={
            "Authorization": f"Bearer {tok}",
            "X-Agent-Run-Id": f"live-personnel-{int(time.time())}",
        },
        json={
            "messages": [{"role": "user", "content": PERSONNEL_QUERY}],
            "kb_scope": {"selected_folder_ids": [FOLDER_JINGPIN_CAIBAO_25]},
            "agent_mode": "deep",
            "orientg_chat_session_id": f"s_personnel_live_{int(time.time())}",
        },
        timeout=720,
    )
    assert r.status_code == 200, r.text[:500]
    events = _parse_sse(r.text)
    done = next((e for e in events if e.get("type") == "done"), None)
    assert done, "no done event"
    reply = str(done.get("reply") or "")
    stats = done.get("hermes_stream_stats") or {}
    hermes_kb = int(stats.get("hermes_orientg_kb_ask_calls") or 0)
    assert hermes_kb >= 1, stats
    assert hermes_kb <= 6, f"kb_ask loop? stats={stats}"
    assert "权限受限" not in reply, reply[:300]
    assert not re.search(r"doc allowed scope empty", reply, re.I)
    # 人员结构终稿：两家主体 + 人员相关表，且非担保/损益等噪声 dump
    assert re.search(r"可比公司A|可比公司A", reply)
    assert re.search(r"YYCQ", reply)
    assert re.search(r"研发人员|1\.1信息-人员|员工|人数", reply)
    assert "连带责任保证" not in reply
    assert "营业收入合计" not in reply or "研发人员" in reply
    assert reply.count("\n---\n") < 2
    # KB 实测锚点：可比公司A研发 1,378；YYCQ excel 1.1信息-人员
    assert re.search(r"1[,，]?378|1378", reply), "missing 可比公司A研发人数"
    assert re.search(r"1\.1信息-人员|研发.*70|70\.00", reply), "missing YYCQ人员分项"
    tool_msgs = " ".join(
        str(e.get("message") or "")
        for e in events
        if e.get("type") in ("tool_call", "tool_progress")
    ).lower()
    assert "terminal" not in tool_msgs or "禁止" in tool_msgs or "failed" in tool_msgs


@pytest.fixture
def _enable_native_mcp(monkeypatch):
    from backend.config import settings

    monkeypatch.setattr(settings, "hermes_native_mcp_reply", True)
    # 目标3：L4 必须以 Hermes 主写验收；默认打开 skip supplemental
    monkeypatch.setattr(settings, "hermes_native_skip_supplemental", True)


@pytest.mark.skipif(
    os.environ.get("ORIENTG_HERMES_NATIVE_MCP") != "1",
    reason="set ORIENTG_HERMES_NATIVE_MCP=1 for native live probe",
)
def test_deep_personnel_native_mcp_live(_enable_native_mcp):
    """L4：Hermes 原生 MCP v2 live；可选 skip supplemental。"""
    if not settings.hermes_configured:
        pytest.skip("Hermes not configured")
    tok = _token()
    r = client.post(
        "/api/agent/chat/stream",
        headers={
            "Authorization": f"Bearer {tok}",
            "X-Agent-Run-Id": f"live-native-{int(time.time())}",
        },
        json={
            "messages": [{"role": "user", "content": PERSONNEL_QUERY}],
            "kb_scope": {"selected_folder_ids": [FOLDER_JINGPIN_CAIBAO_25]},
            "agent_mode": "deep",
            "orientg_chat_session_id": f"s_native_live_{int(time.time())}",
        },
        timeout=720,
    )
    assert r.status_code == 200, r.text[:500]
    events = _parse_sse(r.text)
    done = next((e for e in events if e.get("type") == "done"), None)
    assert done, "no done event"
    reply = str(done.get("reply") or "")
    stats = done.get("hermes_stream_stats") or {}
    hermes_kb = int(stats.get("hermes_orientg_kb_ask_calls") or 0)
    gateway_kb = int(stats.get("gateway_orientg_kb_ask_calls") or 0)
    # E：native+deep 人员横比须多轮自核（≥2）；不得靠 retry 凑数
    assert hermes_kb >= 2, f"hermes_orientg_kb_ask_calls must be >=2 (multi-round); stats={stats}"
    # 目标 4：native+deep 人员 — 网关 prefetch/primer 合计显著下降
    max_gw = int(getattr(settings, "hermes_native_prefetch_max_kb_asks", 1) or 0)
    # 验收上限默认 ≤2（可配 max_asks；含 skip primer 后合计）
    assert gateway_kb <= max(2, max_gw), (
        f"gateway_orientg_kb_ask_calls={gateway_kb} exceed slim cap; stats={stats}"
    )
    assert re.search(r"可比公司A|可比公司A", reply)
    assert re.search(r"YYCQ", reply)
    assert re.search(r"1[,，]?378|1378", reply), reply[:400]
    kb_supp = bool(done.get("kb_supplemental"))
    # 目标3 硬断言：不得用 structured gate / 模板刷绿冒充 Hermes 主写
    assert done.get("structured_gate_applied") is not True, (
        f"structured gate must not replace Hermes final; reply_source={done.get('reply_source')} head={reply[:240]}"
    )
    assert done.get("reply_source") == "hermes", (
        f"reply_source must be hermes, got {done.get('reply_source')}; "
        f"structured_gate_applied={done.get('structured_gate_applied')} head={reply[:240]}"
    )
    from backend.services.personnel_compare_report import looks_like_orientg_personnel_template
    from backend.scripts.finance_matrix_personnel_validate import (
        personnel_compare_has_forbidden_leaks,
    )

    assert not looks_like_orientg_personnel_template(reply), "Orient-G template fingerprint in final reply"
    # 宽尺子 B+C：无强制 MCP 重试；主气泡无推算/推断
    retry_n = int(stats.get("hermes_mcp_retry_count") or 0)
    if any(e.get("type") == "status" and e.get("step") == "hermes_mcp_retry" for e in events):
        retry_n = max(retry_n, 1)
    assert retry_n == 0, f"hermes_mcp_retry must be 0 (wide ruler B); stats={stats}"
    leaks = personnel_compare_has_forbidden_leaks(reply)
    assert "unsupported_speculation" not in leaks, f"speculation in final reply: {leaks}; head={reply[:300]}"
    assert re.search(r"人员结构对照", reply), "missing 人员结构对照"
    if os.environ.get("ORIENTG_HERMES_NATIVE_SKIP_SUPPLEMENTAL") == "1":
        assert not kb_supp, f"expected no supplemental when native skip on; stats={stats}"
