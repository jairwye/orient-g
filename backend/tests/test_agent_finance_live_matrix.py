"""
财务验收矩阵 · 全量 Live 流式实测（finance_test + 竞品财报25 + Hermes/MCP）。

运行约束（必须遵守）：
  - **严格串行**：禁止 pytest-xdist（勿加 -n）；禁止同时开多个 live 矩阵 shell
  - **每条须等流式 done**：TestClient 会阻塞到 SSE `type=done`；勿提前发下一条
  - **本地 LLM 仅 2 路并行**：矩阵用例一次只跑 1 条；用例间默认冷却 5s（可设 ORIENTG_LIVE_MATRIX_CASE_COOLDOWN_S）

运行（耗时长）：
  cd backend
  set ORIENTG_LIVE_FINANCE_MATRIX=1
  python -m pytest tests/test_agent_finance_live_matrix.py -v -s --tb=short

仅快档：
  set ORIENTG_LIVE_FINANCE_MATRIX=fast_only

仅标准档：
  set ORIENTG_LIVE_FINANCE_MATRIX=standard_only

仅深度档：
  set ORIENTG_LIVE_FINANCE_MATRIX=deep_only

页面实测见同目录报告 backend/tests/reports/finance_matrix_live_report.json
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.config import settings
from backend.main import app
from backend.routers.settings import DEPARTMENT_FINANCE
from backend.services.dev_users import ensure_department_test_user
from backend.services.evidence_reply_align import reply_has_derived_breakdown_amounts, reply_has_compare_structure
from backend.services.hermes_stream_sanitize import (
    finalize_agent_reply,
    reply_has_unsupported_estimates,
    reply_has_verifiable_breakdown_table,
)
from backend.tests.finance_matrix_evidence import (
    probe_subject_kb,
    reply_matches_kb,
    reply_says_honest_missing,
)
from backend.tests.test_acl_folder_shared_docs import FOLDER_JINGPIN_CAIBAO_25
from backend.tests.test_agent_finance_acceptance_matrix import MATRIX_ROWS, TIER_CASES

pytest_plugins = ["backend.tests.live_matrix_serial"]

REPORT_PATH = Path(__file__).resolve().parent / "reports" / "finance_matrix_live_report.json"

pytestmark = pytest.mark.skipif(
    os.environ.get("ORIENTG_LIVE_FINANCE_MATRIX")
    not in ("1", "fast_only", "standard_only", "deep_only"),
    reason="set ORIENTG_LIVE_FINANCE_MATRIX=1 (or fast_only / standard_only / deep_only)",
)


@pytest.fixture(autouse=True)
def _reset_llm_circuit_between_cases():
    from backend.services.ollama_guard import reset_llm_circuits_for_tests

    reset_llm_circuits_for_tests()
    yield
    reset_llm_circuits_for_tests()


client = TestClient(app)

_TIMEOUT = {"fast": 180, "standard": 720, "deep": 720}


def _finance_token() -> str:
    ensure_department_test_user(
        "finance_test",
        password="FinanceTest!2026",
        department=DEPARTMENT_FINANCE,
    )
    r = client.post(
        "/api/auth/login",
        json={"username": "finance_test", "password": "FinanceTest!2026"},
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _parse_sse(text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for block in text.split("\n\n"):
        for line in block.split("\n"):
            if not line.strip().startswith("data:"):
                continue
            raw = line.strip()[5:].strip()
            if not raw or raw == "[DONE]":
                continue
            try:
                events.append(json.loads(raw))
            except json.JSONDecodeError:
                continue
    return events


def _score_reply(
    reply: str,
    *,
    query: str,
    category: str,
    subject: str,
    kb_probe: dict[str, Any] | None,
) -> dict[str, bool]:
    t = finalize_agent_reply(reply, user_query=query)
    has_money = bool(re.search(r"\d{1,3}(?:,\d{3})+\.\d{2}", t))
    honest_missing = reply_says_honest_missing(t)
    kb_match = reply_matches_kb(t, subject=subject, kb_probe=kb_probe or {"has_data": True})
    return {
        "min_len": len(t.strip()) >= 120,
        "has_money_or_honest_missing": has_money or honest_missing,
        "has_table_or_structure": reply_has_compare_structure(t),
        "no_derived": not reply_has_derived_breakdown_amounts(t),
        "no_estimate": not reply_has_unsupported_estimates(t),
        "no_gap_with_table": not (
            "证据中未提供可核查的分项金额" in t and reply_has_verifiable_breakdown_table(t)
        ),
        "no_glued_pipe": "。|项目" not in t and "数据。|项目" not in t,
        "kb_data_match": kb_match,
    }


def _run_stream(
    token: str,
    query: str,
    agent_mode: str,
    expected_tier: int,
    *,
    subject: str = "",
    kb_probe: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not settings.hermes_configured and agent_mode in ("standard", "deep"):
        pytest.skip("Hermes not configured")
    if settings.hermes_dev_mock and agent_mode in ("standard", "deep"):
        pytest.skip("hermes_dev_mock blocks live Hermes tiers")

    t0 = time.monotonic()
    r = client.post(
        "/api/agent/chat/stream",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "messages": [{"role": "user", "content": query}],
            "kb_scope": {"selected_folder_ids": [FOLDER_JINGPIN_CAIBAO_25]},
            "allow_kb_write": False,
            "agent_mode": agent_mode,
        },
        timeout=_TIMEOUT.get(agent_mode, 600),
    )
    elapsed = time.monotonic() - t0
    assert r.status_code == 200, r.text[:800]
    events = _parse_sse(r.text)
    done = next((e for e in events if e.get("type") == "done"), None)
    assert done, f"no done in {len(events)} events, elapsed={elapsed:.0f}s"
    # 须等到终稿落盘：reply 非空，或明确 error/cancelled
    reply = str(done.get("reply") or "").strip()
    if done.get("ok") is not False and not reply:
        pytest.fail(f"done without reply body, elapsed={elapsed:.0f}s events={len(events)}")
    tier = done.get("agent_tier")
    scores = _score_reply(
        reply,
        query=query,
        category="",
        subject=subject,
        kb_probe=kb_probe,
    )
    stats = done.get("hermes_stream_stats") or {}
    kb_ask = int(stats.get("orientg_kb_ask_calls") or 0) if isinstance(stats, dict) else 0
    return {
        "elapsed_s": round(elapsed, 1),
        "agent_tier": tier,
        "agent_route": done.get("agent_route"),
        "kb_supplemental": bool(done.get("kb_supplemental")),
        "kb_ask_calls": kb_ask,
        "reply_len": len(reply),
        "scores": scores,
        "reply_head": reply[:400],
        "tier_ok": tier == expected_tier,
        "kb_probe": kb_probe,
        "all_scores_ok": all(scores.values()),
    }


def _append_report(row: dict[str, Any]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    if REPORT_PATH.exists():
        try:
            rows = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            rows = []
    rows.append(row)
    REPORT_PATH.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def _tier_filter(mode_name: str) -> bool:
    only = os.environ.get("ORIENTG_LIVE_FINANCE_MATRIX", "1")
    if only == "1":
        return True
    if only == "fast_only":
        return mode_name == "fast"
    if only == "standard_only":
        return mode_name == "standard"
    if only == "deep_only":
        return mode_name == "deep"
    return True


@pytest.fixture(scope="function")
def finance_token() -> str:
    """每条用例重新登录，避免长矩阵跑完 token 过期（401）。"""
    return _finance_token()


@pytest.fixture(scope="module")
def kb_probes() -> dict[str, dict[str, Any]]:
    """各矩阵问句 KB 锚点（module 级串行探测，探测间短冷却）。"""
    from backend.tests.finance_matrix_evidence import probe_subject_kb
    from backend.tests.live_matrix_serial import case_cooldown_seconds

    token = _finance_token()
    out: dict[str, dict[str, Any]] = {}
    cd = min(case_cooldown_seconds(), 2.0)
    for _category, subject, query in MATRIX_ROWS:
        key = f"{subject}::{query}"
        if key not in out:
            out[key] = probe_subject_kb(token, subject, user_query=query)
            if cd > 0:
                time.sleep(cd)
    return out


@pytest.mark.parametrize("category,subject,query", MATRIX_ROWS)
@pytest.mark.parametrize("mode_name,agent_mode,expected_tier", TIER_CASES)
def test_live_matrix_stream(
    finance_token: str,
    kb_probes: dict[str, dict[str, Any]],
    category: str,
    subject: str,
    query: str,
    mode_name: str,
    agent_mode: str,
    expected_tier: int,
):
    if not _tier_filter(mode_name):
        pytest.skip(f"ORIENTG_LIVE_FINANCE_MATRIX filter skips {mode_name}")

    probe = kb_probes.get(f"{subject}::{query}") or {"has_data": True, "anchors": []}
    result = _run_stream(
        finance_token,
        query,
        agent_mode,
        expected_tier,
        subject=subject,
        kb_probe=probe,
    )
    row = {
        "at": datetime.now(timezone.utc).isoformat(),
        "category": category,
        "subject": subject,
        "mode": mode_name,
        "query": query,
        **result,
    }
    _append_report(row)
    print(
        f"\n[{category}/{subject}/{mode_name}] tier={result['agent_tier']} "
        f"elapsed={result['elapsed_s']}s supplemental={result['kb_supplemental']} "
        f"scores={result['scores']}"
    )
    assert result["tier_ok"], (
        f"expected tier {expected_tier}, got {result['agent_tier']} route={result['agent_route']}"
    )
    missing = [k for k, ok in result["scores"].items() if not ok]
    if not result["all_scores_ok"]:
        probe = result.get("kb_probe") or {}
        hint = (
            f"KB has_data={probe.get('has_data')} anchors={probe.get('anchors')[:3]}"
            if probe.get("has_data") and "kb_data_match" in missing
            else ""
        )
        assert result["all_scores_ok"], (
            f"score failures: {missing}; {hint}; head={result['reply_head'][:200]}"
        )
