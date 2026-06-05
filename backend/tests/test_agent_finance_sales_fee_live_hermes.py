"""财务部 + 竞品财报25 + 真实 Hermes 深度轮（慢测，单次串行）。

运行（勿并行，避免 LLM 过载）：
  cd backend
  set ORIENTG_LIVE_HERMES=1
  python -m pytest tests/test_agent_finance_sales_fee_live_hermes.py -q -s --tb=short

基准：Hermes **原生**终稿（Orient-G 仅预检索+规制+剥离过程稿，禁止网关追加段落）。
"""

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

QUERY = "出一份华清25、24两年销售费用明细的对比分析报告"

# 附注分项锚点（验收用，非生产硬编码）
FEE_TOTAL_2025 = "13,722,360.23"
FEE_TOTAL_2024 = "25,081,092.51"
PAYROLL_2025 = "10,802,366.11"
PAYROLL_2024 = "23,295,127.31"
MKT_2025 = "2,889,547.75"
REV_2025 = "100,148,026.24"

pytestmark = pytest.mark.skipif(
    os.environ.get("ORIENTG_LIVE_HERMES") != "1",
    reason="set ORIENTG_LIVE_HERMES=1 for live Hermes run (slow, serial only)",
)

client = TestClient(app)


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


def _parse_sse(text: str) -> list[dict]:
    events: list[dict] = []
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


def _wan_label(yuan: str) -> str:
    n = float(yuan.replace(",", ""))
    wan = n / 10000.0
    return f"{wan:,.2f}" if wan >= 1000 else f"{wan:.2f}"


def _amount_in_reply(text: str, yuan: str) -> bool:
    if yuan in text:
        return True
    wan = _wan_label(yuan)
    wan_alt = wan.replace(",", "")
    return bool(
        re.search(rf"{re.escape(wan)}\s*万", text)
        or re.search(rf"{re.escape(wan_alt)}\s*万", text)
    )


def _score_reply(reply: str) -> dict[str, bool]:
    t = reply or ""
    return {
        "has_fee_total": _amount_in_reply(t, FEE_TOTAL_2025) and _amount_in_reply(t, FEE_TOTAL_2024),
        "has_payroll_exact": _amount_in_reply(t, PAYROLL_2025) and _amount_in_reply(t, PAYROLL_2024),
        "has_marketing_line": _amount_in_reply(t, MKT_2025),
        "has_revenue_context": _amount_in_reply(t, REV_2025) or "销售费用率" in t or "费比" in t,
        "has_table": "|" in t and ("2025" in t or "2024" in t),
        "no_estimate_hallucination": not bool(
            re.search(r"约\s*[\d,.]+万|[\d]{1,3}\s*[-~至]\s*[\d]{1,3}\s*万|减少约|增加约", t)
        )
        and "约 xxx" not in t.lower(),
        "min_length": len(t.strip()) >= 600,
        "has_change_reason": bool(
            re.search(r"(主要系|主要是由于|人员减少|变动原因|职工薪酬减少)", t)
        ),
        "no_gateway_appendix": "补充检索（Orient-G 网关）" not in t,
        "has_structure": bool(re.search(r"(#{1,4}\s|^\d+\.\s|\*\*结论|结论[：:])", t, re.M)),
        "has_markdown_headers": bool(re.search(r"^#{2,4}\s", t, re.M)),
        "has_revenue_and_fee_ratio": _amount_in_reply(t, REV_2025) and "销售费用率" in t,
        "has_analyst_depth": bool(
            re.search(r"(盈利能力|费比影响|分项驱动|风险提示|总结与后续|八、|七、)", t)
        ),
    }


def test_live_deep_agent_sales_fee_report():
    if not settings.hermes_configured or settings.hermes_dev_mock:
        pytest.skip("Hermes not configured for live run")

    token = _finance_token()
    t0 = time.monotonic()
    r = client.post(
        "/api/agent/chat/stream",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "messages": [{"role": "user", "content": QUERY}],
            "kb_scope": {"selected_folder_ids": [FOLDER_JINGPIN_CAIBAO_25]},
            "allow_kb_write": False,
            "agent_mode": "deep",
        },
        timeout=600,
    )
    elapsed = time.monotonic() - t0
    assert r.status_code == 200, r.text[:500]
    events = _parse_sse(r.text)
    done = next((e for e in events if e.get("type") == "done"), None)
    assert done, f"no done event in {len(events)} events, elapsed={elapsed:.0f}s"

    assert done.get("agent_tier") == 2, done.get("agent_route")
    reply = str(done.get("reply") or "").strip()
    assert reply, "empty reply"

    scores = _score_reply(reply)
    missing = [k for k, ok in scores.items() if not ok]
    stats = (done.get("hermes_stream_stats") or {}) if isinstance(done.get("hermes_stream_stats"), dict) else {}
    kb_ask = int(stats.get("orientg_kb_ask_calls") or 0)

    assert not done.get("kb_supplemental"), "Tier 2 must not run gateway supplemental on reply"
    assert done.get("supplemental_mode") != "tier2_gap_append"

    head = reply[:500]
    assert "skill不相关" not in head, "orchestration preamble leaked into reply"
    assert "orientg_kb_ask`" not in head and not head.startswith("先根据"), "planning leaked"
    assert reply.lstrip().startswith("#") or "结论" in reply[:120], "reply should start with report"

    # 打印供人工核对（pytest -s）
    print(f"\n--- live hermes deep elapsed={elapsed:.0f}s kb_ask={kb_ask} len={len(reply)} ---")
    print(f"scores={scores}")
    print(reply[:2500])
    if len(reply) > 2500:
        print("...(truncated)...")

    assert scores["has_fee_total"], f"missing fee totals; missing={missing}"
    assert scores["has_payroll_exact"], f"missing payroll line items; missing={missing}"
    assert scores["no_estimate_hallucination"], "reply contains 估算 hallucination"
    assert scores["has_table"], "missing markdown table"
    assert scores["min_length"], f"reply too short ({len(reply)} chars)"
    assert scores["no_gateway_appendix"], "gateway appendix must not be appended to Tier 2 reply"
    assert scores["has_structure"], f"missing report headings; missing={missing}"
    assert scores["has_markdown_headers"], f"missing ##/#### headings; missing={missing}"
    assert scores["has_revenue_and_fee_ratio"], f"missing revenue/fee-ratio; missing={missing}"
    assert scores["has_revenue_context"], f"missing revenue/fee-ratio context; missing={missing}"
    assert scores["has_change_reason"], f"missing change reason from evidence; missing={missing}"
    assert scores["has_analyst_depth"], f"missing analyst sections (profit/risk/summary); missing={missing}"
