"""Agent KB 路由规则单测（Tier 0–2）。"""

from __future__ import annotations

import pytest

from backend.services.agent_kb_router import AgentRoute, resolve_agent_route, route_to_agent_tier

PREFETCH_OK = {
    "ok": True,
    "citations": [{"doc_id": "d1"}, {"doc_id": "d2"}, {"doc_id": "d3"}],
    "evidence_pack": {
        "task_type": "compare",
        "coverage_score": 0.85,
        "gaps": [],
        "citations": [{"doc_id": "d1"}, {"doc_id": "d2"}, {"doc_id": "d3"}],
        "facets": [{"keywords_hit": ["营业收入", "合并利润表"]}],
    },
}

PREFETCH_GAPS = {
    "ok": True,
    "citations": [{"doc_id": "d1"}],
    "evidence_pack": {
        "task_type": "compare",
        "coverage_score": 0.35,
        "gaps": ["未命中合并利润表"],
        "facets": [],
    },
}


@pytest.mark.parametrize(
    "query,mode,allow_write,has_kb,expected",
    [
        ("华清25年营收是多少", "fast", False, True, AgentRoute.fast),
        ("做华清25和24年损益对比表", "standard", False, True, AgentRoute.hermes_lite),
        ("做华清25和24年损益对比表", "auto", False, True, AgentRoute.hermes_lite),
        ("上传文档到公共库", "standard", True, True, AgentRoute.hermes_full),
        ("核实并再查一遍营收", "standard", False, True, AgentRoute.hermes_lite),
        ("你好", "standard", False, False, AgentRoute.hermes_lite),
    ],
)
def test_resolve_route_query_and_mode(query, mode, allow_write, has_kb, expected):
    prefetch = PREFETCH_OK if has_kb else None
    if "核实" in query:
        prefetch = PREFETCH_GAPS
    got = resolve_agent_route(
        user_query=query,
        agent_mode=mode,
        allow_kb_write=allow_write,
        has_kb_scope=has_kb,
        prefetch_result=prefetch,
        hermes_configured=True,
    )
    assert got == expected


def test_fast_mode_with_gaps_stays_tier0():
    """规制：快速模式强制 Tier 0，证据不足不升 Hermes。"""
    got = resolve_agent_route(
        user_query="做华清25和24年损益对比表",
        agent_mode="fast",
        allow_kb_write=False,
        has_kb_scope=True,
        prefetch_result=PREFETCH_GAPS,
        hermes_configured=True,
    )
    assert got == AgentRoute.fast


def test_auto_breakdown_detail_query_routes_hermes_lite():
    """auto + 明细/对比类问句：即使 pack 覆盖率够也升 Hermes lite。"""
    got = resolve_agent_route(
        user_query="出一份华清25、24两年销售费用明细的对比分析报告",
        agent_mode="auto",
        allow_kb_write=False,
        has_kb_scope=True,
        prefetch_result=PREFETCH_OK,
        hermes_configured=True,
    )
    assert got == AgentRoute.hermes_lite


def test_standard_with_gaps_routes_hermes_lite():
    got = resolve_agent_route(
        user_query="做华清25和24年损益对比表",
        agent_mode="standard",
        allow_kb_write=False,
        has_kb_scope=True,
        prefetch_result=PREFETCH_GAPS,
        hermes_configured=True,
    )
    assert got == AgentRoute.hermes_lite


def test_auto_simple_query_routes_fast(monkeypatch):
    from backend.config import settings

    monkeypatch.setattr(settings, "hermes_agent_simple_query_fast", True)
    monkeypatch.setattr(settings, "hermes_agent_kb_fast_path", False)
    prefetch = {
        **PREFETCH_OK,
        "citations": [{"doc_id": "d1"}, {"doc_id": "d2"}],
        "evidence_pack": {
            "task_type": "fact",
            "coverage_score": 0.8,
            "gaps": [],
            "citations": [{"doc_id": "d1"}, {"doc_id": "d2"}],
            "facets": [{"keywords_hit": ["营业收入"]}],
        },
    }
    got = resolve_agent_route(
        user_query="华清25年营收是多少",
        agent_mode="auto",
        allow_kb_write=False,
        has_kb_scope=True,
        prefetch_result=prefetch,
        hermes_configured=True,
    )
    assert got == AgentRoute.fast


def test_route_to_tier_mapping():
    assert route_to_agent_tier(AgentRoute.fast) == 0
    assert route_to_agent_tier(AgentRoute.hermes_lite) == 1
    assert route_to_agent_tier(AgentRoute.hermes_full) == 2
