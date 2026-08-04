"""Hermes 原生 MCP 探针：P1–P3 人员 + F1 财务（单元 + Live KB 直连）。"""

from __future__ import annotations

import os
import re
import time

import jwt
import pytest

from backend.config import settings
from backend.services import hermes_token_bridge as bridge
from backend.services import orientg_mcp_tools as tools
from backend.services.kb_ask_mcp_agent_native import (
    build_agent_payload,
    detect_kb_task_type,
)
from backend.services.hermes_client import _register_session
from backend.tests.test_acl_folder_shared_docs import FOLDER_JINGPIN_CAIBAO_25

PROBE_P1 = "对比分析YYCQ和可比公司A25年的人员结构"
PROBE_P2 = "可比公司A2025研发人员数量及占比"
PROBE_P3 = "YYCQ2025员工专业构成"
PROBE_F1 = "对比YYCQ与可比公司A2025年销售费用率"

LIVE_KB = pytest.mark.skipif(
    os.environ.get("ORIENTG_LIVE_NATIVE_MCP") != "1",
    reason="set ORIENTG_LIVE_NATIVE_MCP=1 for live KB MCP probes",
)


def _jwt(sub: str = "finance_test") -> str:
    return jwt.encode(
        {"sub": sub, "iat": int(time.time()), "exp": int(time.time()) + 3600},
        settings.auth_secret,
        algorithm="HS256",
    )


@pytest.fixture(autouse=True)
def _reset_bridge():
    bridge.reset_for_tests()
    yield
    bridge.reset_for_tests()


@pytest.fixture
def native_session(monkeypatch):
    monkeypatch.setattr(settings, "hermes_native_mcp_reply", True)
    tok = _jwt()
    sk = _register_session(
        tok,
        f"s_probe_{int(time.time() * 1000)}",
        username="finance_test",
        orientg_chat_session_id=f"s_probe_{int(time.time())}",
        kb_scope={"selected_folder_ids": [FOLDER_JINGPIN_CAIBAO_25]},
        orientg_route="hermes_full",
    )
    return tok, sk


def test_probe_task_types():
    assert detect_kb_task_type(PROBE_P1) == "personnel_compare"
    assert detect_kb_task_type(PROBE_P2) == "personnel_compare"
    assert detect_kb_task_type(PROBE_P3) == "personnel_compare"
    assert detect_kb_task_type(PROBE_F1) == "finance_compare"


def test_probe_p2_single_entity_payload_sufficient():
    payload = build_agent_payload(
        query=PROBE_P2,
        excerpts=[
            {
                "entity": "可比公司A",
                "doc_id": "ud_a",
                "excerpt": "研发人员数量 1,378 占比 43.91%",
            }
        ],
        citations=[{"doc_id": "ud_a"}],
    )
    assert payload["evidence_sufficient"] is True
    assert payload["evidence"][0]["metrics"].get("rd_headcount") == 1378


def test_probe_f1_finance_payload_contract():
    payload = build_agent_payload(
        query=PROBE_F1,
        excerpts=[
            {"entity": "可比公司A", "doc_id": "ud_a", "excerpt": "销售费用 12.3 亿元 销售费用率 8.5%"},
            {"entity": "YYCQ", "doc_id": "ud_b", "excerpt": "销售费用 1,200 万元"},
        ],
        citations=[{"doc_id": "ud_a"}, {"doc_id": "ud_b"}],
    )
    assert payload["task_type"] == "finance_compare"
    assert payload["evidence_sufficient"] is True
    assert "### 核心指标对照" in payload["output_contract"]["required_sections"]
    assert payload["suggested_queries_if_insufficient"] == []


@LIVE_KB
def test_live_kb_mcp_probe_p1(native_session):
    tok, sk = native_session
    out = tools.orientg_kb_ask(tok, PROBE_P1, hermes_session_key=sk)
    assert out.get("ok") is True, out
    payload = out.get("agent_payload") or {}
    assert payload.get("schema") == "orientg_kb_ask_v2"
    reply = str(out.get("reply") or "")
    assert "orientg_kb_ask_v2" in reply
    assert re.search(r"1378|1[,，]?378", reply) or re.search(r"1378|1[,，]?378", str(payload))


@LIVE_KB
def test_live_kb_mcp_probe_p2(native_session):
    tok, sk = native_session
    out = tools.orientg_kb_ask(tok, PROBE_P2, hermes_session_key=sk)
    assert out.get("ok") is True, out
    payload = out.get("agent_payload") or {}
    assert payload.get("task_type") == "personnel_compare"
    reply = str(out.get("reply") or "")
    assert re.search(r"研发|1378|1[,，]?378", reply, re.I)


@LIVE_KB
def test_live_kb_mcp_probe_p3(native_session):
    tok, sk = native_session
    out = tools.orientg_kb_ask(tok, PROBE_P3, hermes_session_key=sk)
    assert out.get("ok") is True, out
    reply = str(out.get("reply") or "")
    assert re.search(r"1\.1信息-人员|专业构成|运营|研发", reply, re.I)


@LIVE_KB
def test_live_kb_mcp_probe_f1(native_session):
    tok, sk = native_session
    out = tools.orientg_kb_ask(tok, PROBE_F1, hermes_session_key=sk)
    assert out.get("ok") is True, out
    payload = out.get("agent_payload") or {}
    assert payload.get("task_type") == "finance_compare"
    reply = str(out.get("reply") or "")
    assert re.search(r"销售费用|费用率|销售", reply, re.I)
