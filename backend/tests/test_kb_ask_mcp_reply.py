"""orientg_kb_ask MCP 回复须含证据节选，供 Hermes 直接成稿。"""

from __future__ import annotations

import jwt
import time
from unittest.mock import patch

import pytest

from backend.config import settings
from backend.database import init_hermes_session_store_table
from backend.services import hermes_shared_session as shared
from backend.services import hermes_token_bridge as bridge
from backend.services import orientg_mcp_tools as tools
from backend.services.kb_ask_mcp_reply import build_kb_ask_mcp_reply
from backend.services.hermes_client import _register_session
from backend.tests.test_acl_folder_shared_docs import FOLDER_JINGPIN_CAIBAO_25

PERSONNEL_QUERY = "对比分析YYCQ和可比公司A25年的人员结构"


@pytest.fixture(autouse=True)
def _reset():
    init_hermes_session_store_table()
    bridge.reset_for_tests()
    shared.reset_for_tests()
    yield
    bridge.reset_for_tests()
    shared.reset_for_tests()


def _jwt(sub: str = "finance_test") -> str:
    return jwt.encode(
        {"sub": sub, "iat": int(time.time()), "exp": int(time.time()) + 3600},
        settings.auth_secret,
        algorithm="HS256",
    )


def test_build_personnel_compare_excerpts_uses_folder_label_when_chunk_has_no_company_name():
    """切块正文无公司名时，以 doc→子文件夹归属分主体（非正文关键词猜测）。"""
    from backend.services.kb_ask_mcp_reply import build_personnel_compare_excerpts

    cites = [
        {"doc_id": "ud_37", "chunk_id": "c1"},
        {"doc_id": "ud_yy", "chunk_id": "c2"},
    ]
    labels = {"ud_37": "可比公司A", "ud_yy": "YYCQ"}

    def fake_load(_tid, did, _cid, _seq):
        if did == "ud_37":
            return "## 公司研发人员情况\n研发人员数量 1,378 占比 43.91%"
        if did == "ud_yy":
            return "## 1.1信息-人员\n研发 70 运营 61"
        return ""

    with patch("backend.services.ai_interaction_llm._load_doc_chunk_text", side_effect=fake_load):
        excerpts = build_personnel_compare_excerpts(
            cites,
            PERSONNEL_QUERY,
            tenant_id="tenant1",
            fixtures={},
            doc_folder_labels=labels,
        )
    assert len(excerpts) == 2
    texts = " ".join(x["excerpt"] for x in excerpts)
    assert "1,378" in texts
    assert "1.1信息-人员" in texts


def test_build_personnel_compare_excerpts_picks_per_entity():
    from backend.services.kb_ask_mcp_reply import build_personnel_compare_excerpts

    cites = [
        {"doc_id": "ud_a", "chunk_id": "c1"},
        {"doc_id": "ud_b", "chunk_id": "c2"},
        {"doc_id": "ud_c", "chunk_id": "c3"},
    ]
    labels = {"ud_a": "可比公司A2025年报", "ud_b": "YYCQ2025"}

    def fake_load(_tid, did, _cid, _seq):
        if did == "ud_a":
            return "## 公司研发人员情况\n研发人员数量（人） 1,378 研发人员数量占比 43.91%"
        if did == "ud_b":
            return "## 1.1信息-人员\n**公司**: YYCQ | 研发 70.00 运营 61.00"
        return "## 5、现金流\n经营活动产生的现金流量净额"

    with patch("backend.services.ai_interaction_llm._load_doc_chunk_text", side_effect=fake_load):
        excerpts = build_personnel_compare_excerpts(
            cites,
            PERSONNEL_QUERY,
            tenant_id="tenant1",
            fixtures={},
            doc_folder_labels=labels,
        )
    assert len(excerpts) == 2
    ents = {x.get("entity") for x in excerpts}
    assert any("可比公司A" in (e or "") for e in ents)
    assert any("YYCQ" in (e or "") for e in ents)


def test_personnel_excerpt_reply_is_low_quality_detects_noise_dump():
    from backend.services.kb_ask_mcp_reply import personnel_excerpt_reply_is_low_quality

    bad = "## 对比\n---\n营业收入合计 159亿\n---\n连带责任保证"
    assert personnel_excerpt_reply_is_low_quality(bad)
    good = "## YYCQ vs 可比公司A\n### 可比公司A\n研发人员 1378\n### YYCQ\n1.1信息-人员"
    assert not personnel_excerpt_reply_is_low_quality(good)
    md_table = (
        "## 对比\n| 岗位 | 人数 |\n| --- | --- |\n| 研发 | 70.00 |\n| 运营 | 61.00 |"
    )
    assert not personnel_excerpt_reply_is_low_quality(md_table)


def test_extract_query_entity_phrases_personnel_compare():
    from backend.services.kb_retrieval_plan import extract_query_entity_phrases

    ents = extract_query_entity_phrases(PERSONNEL_QUERY)
    assert "YYCQ" in ents
    assert "可比公司A" in ents
    assert not any(e.startswith("对比") for e in ents)


def test_format_personnel_compare_report_structured():
    from backend.services.kb_ask_mcp_reply import format_personnel_compare_report

    out = format_personnel_compare_report(
        [
            {"entity": "可比公司A", "excerpt": "研发人员 1,378"},
            {"entity": "YYCQ", "excerpt": "1.1信息-人员 研发 70"},
        ]
    )
    assert out
    assert "### 人员结构对照" in out
    assert "### 对比分析" in out


def test_build_kb_ask_mcp_reply_uses_personnel_excerpts_when_available():
    res = {
        "reply": "混合检索命中 3 条证据。",
        "citations": [
            {"doc_id": "ud_a", "chunk_id": "c1"},
            {"doc_id": "ud_b", "chunk_id": "c2"},
        ],
    }
    with patch(
        "backend.services.kb_ask_mcp_reply.build_personnel_compare_excerpts",
        return_value=[
            {"doc_id": "ud_a", "chunk_id": "c1", "excerpt": "[可比公司A]\n研发人员情况 3138"},
            {"doc_id": "ud_b", "chunk_id": "c2", "excerpt": "[YYCQ]\n1.1信息-人员 158"},
        ],
    ):
        out, excerpts = build_kb_ask_mcp_reply(res, query=PERSONNEL_QUERY, tenant_id="tenant1", fixtures={})
    assert "人员结构证据节选" in out
    assert "3138" in out
    assert "158" in out
    assert len(excerpts) == 2


def test_build_kb_ask_mcp_reply_includes_excerpts():
    res = {
        "reply": "混合检索命中 2 条证据。",
        "citations": [
            {"doc_id": "ud_a", "chunk_id": "c1", "chunk_seq_no": 1, "score": 0.9},
            {"doc_id": "ud_b", "chunk_id": "c2", "chunk_seq_no": 2, "score": 0.8},
        ],
    }
    with patch(
        "backend.services.agent_kb_prefetch.build_prefetch_evidence_excerpts",
        return_value=[
            {"doc_id": "ud_a", "chunk_id": "c1", "excerpt": "可比公司A 2025年末人数 3,138"},
            {"doc_id": "ud_b", "chunk_id": "c2", "excerpt": "YYCQ 2025年末人数 158"},
        ],
    ):
        out, excerpts = build_kb_ask_mcp_reply(res, query=PERSONNEL_QUERY, tenant_id="tenant1", fixtures={})
    assert "证据节选" in out
    assert "3,138" in out
    assert "158" in out
    assert "混合检索命中" in out
    assert len(excerpts) == 2


@patch("backend.services.knowledge_pipeline.ask_knowledge")
def test_orientg_kb_ask_mcp_reply_has_excerpt_body(mock_ask):
    mock_ask.return_value = {
        "reply": "已在权限范围内匹配到文档证据（2 条）。",
        "citations": [{"doc_id": "ud_x", "chunk_id": "c1", "chunk_seq_no": 1}],
    }
    with patch(
        "backend.services.agent_kb_prefetch.build_prefetch_evidence_excerpts",
        return_value=[{"doc_id": "ud_x", "chunk_id": "c1", "excerpt": "可比公司A 研发人员情况 3138"}],
    ):
        tok = _jwt()
        sk = _register_session(
            tok,
            "s_mcp_excerpt",
            username="finance_test",
            orientg_chat_session_id="s_mcp_excerpt",
            kb_scope={"selected_folder_ids": [FOLDER_JINGPIN_CAIBAO_25]},
            orientg_route="hermes_full",
        )
        bridge.reset_for_tests()
        res = tools.orientg_kb_ask("", PERSONNEL_QUERY, hermes_session_key=sk)
    assert res.get("ok") is True
    reply = str(res.get("reply") or "")
    assert "证据节选" in reply
    assert "3138" in reply
    assert res.get("evidence_excerpts")


def test_personnel_compare_excerpt_is_valid():
    from backend.services.kb_ask_mcp_reply import personnel_compare_excerpt_is_valid

    from backend.scripts.finance_matrix_personnel_validate import GOOD_PERSONNEL_COMPARE_EXCERPT

    assert personnel_compare_excerpt_is_valid(GOOD_PERSONNEL_COMPARE_EXCERPT, user_query=PERSONNEL_QUERY)
    assert not personnel_compare_excerpt_is_valid("缺少可比公司A数据", user_query=PERSONNEL_QUERY)


def test_personnel_compare_reply_misattributed():
    from backend.services.kb_ask_mcp_reply import personnel_compare_reply_misattributed

    bad = "YYCQ研发人员 95人 vs 1,378人，可比公司A人员结构缺失证据"
    assert personnel_compare_reply_misattributed(bad, user_query=PERSONNEL_QUERY)
    assert not personnel_compare_reply_misattributed(
        "### 可比公司A\n1,378\n### YYCQ\n1.1信息-人员",
        user_query=PERSONNEL_QUERY,
    )
    good_table = (
        "## 人员结构对照\n| 指标 | YYCQ | 可比公司A |\n| --- | --- | --- |\n"
        "| 研发 | 70 | 1,378 |\n### 对比分析\n结构差异。\n"
    )
    assert not personnel_compare_reply_misattributed(good_table, user_query=PERSONNEL_QUERY)


def test_personnel_excerpt_fallback_from_prefetch():
    from backend.services.kb_ask_mcp_reply import personnel_compare_reply_from_prefetch

    with patch(
        "backend.services.kb_ask_mcp_reply.build_personnel_compare_excerpts",
        return_value=[
            {"entity": "可比公司A", "doc_id": "ud_a", "chunk_id": "c1", "excerpt": "研发人员 3,138"},
            {"entity": "YYCQ", "doc_id": "ud_b", "chunk_id": "c2", "excerpt": "1.1信息-人员 158"},
        ],
    ):
        out = personnel_compare_reply_from_prefetch(
            {
                "citations": [{"doc_id": "ud_a", "chunk_id": "c1"}, {"doc_id": "ud_b", "chunk_id": "c2"}],
                "evidence_pack": {"doc_folder_labels": {}},
            },
            user_query="对比分析YYCQ和可比公司A25年的人员结构",
            tenant_id="tenant1",
            fixtures={},
        )
    assert out
    assert "人员结构对照" in out
    assert "分主体证据摘要" not in out
    assert "营业收入合计" not in out


def test_personnel_excerpt_preserves_staff_table_after_rd_merge():
    from backend.services.kb_ask_mcp_reply import _personnel_entity_excerpt

    rd = "公司研发人员情况\n" + ("研发人员学历结构\n" * 200)
    staff = "1、员工数量、专业构成及教育程度\n| 销售人员 | 946 |\n| 运营人员 | 242 |"
    merged = f"{rd}\n\n{staff}"
    out = _personnel_entity_excerpt(merged, excerpt_cap=2800)
    assert "946" in out
    assert "242" in out


def test_build_personnel_compare_excerpts_merges_sanqi_staff_section():
    from backend.services.kb_ask_mcp_reply import build_personnel_compare_excerpts

    cites = [
        {"doc_id": "ud_rd", "chunk_id": "c1"},
        {"doc_id": "ud_staff", "chunk_id": "c2"},
        {"doc_id": "ud_yy", "chunk_id": "c3"},
    ]
    labels = {"ud_rd": "PeerA25", "ud_staff": "PeerA25", "ud_yy": "YYCQ"}

    def fake_load(_tid, did, _cid, _seq):
        if did == "ud_rd":
            return "## 公司研发人员情况\n研发人员数量（人） | 1,378 | 研发人员数量占比 43.91%"
        if did == "ud_staff":
            return (
                "## 1、员工数量、专业构成及教育程度\n"
                "| 销售人员 | 946 |\n| 运营人员 | 242 |\n| 在职员工的数量合计（人） | 3,138 |"
            )
        if did == "ud_yy":
            return "## 1.1信息-人员\n研发 70 运营 61"
        return ""

    with patch("backend.services.ai_interaction_llm._load_doc_chunk_text", side_effect=fake_load):
        excerpts = build_personnel_compare_excerpts(
            cites,
            PERSONNEL_QUERY,
            tenant_id="tenant1",
            fixtures={},
            doc_folder_labels=labels,
        )
    sanqi = next(x for x in excerpts if "可比公司A" in str(x.get("entity") or ""))
    assert "1,378" in sanqi["excerpt"]
    assert "销售人员" in sanqi["excerpt"]
    assert "946" in sanqi["excerpt"]


def test_boost_personnel_compare_citations_injects_staff_section():
    from backend.services.kb_ask_mcp_reply import (
        boost_personnel_compare_citations,
        build_personnel_compare_excerpts,
    )

    labels = {"ud_rd": "PeerA25", "ud_staff": "PeerA25", "ud_yy": "25"}
    cites = [{"doc_id": "ud_rd", "chunk_id": "c1"}]

    def fake_fetch(_tid, *, doc_ids, sql):
        if "专业构成及教育程度" in sql and "ud_staff" in doc_ids:
            return [{"doc_id": "ud_staff", "chunk_id": "c2", "chunk_seq_no": 1}]
        if "研发人员情况" in sql:
            return [{"doc_id": "ud_rd", "chunk_id": "c1", "chunk_seq_no": 1}]
        if "1.1信息-人员" in sql and "ud_yy" in doc_ids:
            return [{"doc_id": "ud_yy", "chunk_id": "c3", "chunk_seq_no": 1}]
        return []

    def fake_load(_tid, did, _cid, _seq):
        if did == "ud_rd":
            return "## 公司研发人员情况\n研发人员数量（人） | 1,378 | 研发人员数量占比 43.91%"
        if did == "ud_staff":
            return (
                "## 1、员工数量、专业构成及教育程度\n"
                "| 销售人员 | 946 |\n| 运营人员 其他职能部门人员 | 242 319 |"
            )
        if did == "ud_yy":
            return "## 1.1信息-人员\n研发 70 运营 61"
        return ""

    with patch(
        "backend.services.kb_ask_mcp_reply._fetch_scope_personnel_section_citations",
        side_effect=fake_fetch,
    ):
        boosted = boost_personnel_compare_citations(
            cites,
            user_query=PERSONNEL_QUERY,
            tenant_id="tenant1",
            doc_folder_labels=labels,
        )
        assert any(c.get("doc_id") == "ud_staff" for c in boosted)
        with patch("backend.services.ai_interaction_llm._load_doc_chunk_text", side_effect=fake_load):
            excerpts = build_personnel_compare_excerpts(
                boosted,
                PERSONNEL_QUERY,
                tenant_id="tenant1",
                fixtures={},
                doc_folder_labels=labels,
            )
    sanqi = next(x for x in excerpts if "可比公司A" in str(x.get("entity") or ""))
    assert "946" in sanqi["excerpt"]
    assert "242" in sanqi["excerpt"]


def test_boost_personnel_sanqi_staff_single_injects_staff_section():
    from backend.services.kb_ask_mcp_reply import boost_personnel_compare_citations

    labels = {"ud_staff": "PeerA25"}
    with patch(
        "backend.services.kb_ask_mcp_reply._fetch_scope_personnel_section_citations",
        return_value=[{"doc_id": "ud_staff", "chunk_id": "c2", "chunk_seq_no": 1}],
    ):
        boosted = boost_personnel_compare_citations(
            [],
            user_query="可比公司A2025年员工数量、专业构成及教育程度",
            tenant_id="tenant1",
            doc_folder_labels=labels,
        )
    assert any(c.get("doc_id") == "ud_staff" for c in boosted)


def test_personnel_single_subject_reply_from_prefetch_staff():
    from backend.services.kb_ask_mcp_reply import personnel_single_subject_reply_from_prefetch

    staff_txt = (
        "1、员工数量、专业构成及教育程度\n"
        "| 销售人员 | 946 |\n| 运营人员 | 242 |\n"
        "| 在职员工的数量合计（人） | 3,138 |"
    )
    labels = {"ud_staff": "PeerA25"}
    prefetch = {"citations": [{"doc_id": "ud_noise", "chunk_id": "c0", "chunk_seq_no": 0}]}
    with patch(
        "backend.services.kb_ask_mcp_reply.boost_personnel_compare_citations",
        return_value=[{"doc_id": "ud_staff", "chunk_id": "c2", "chunk_seq_no": 1, "source": "personnel_scope_section_boost"}],
    ), patch(
        "backend.services.kb_ask_mcp_reply.resolve_doc_folder_labels",
        return_value=labels,
    ), patch(
        "backend.services.ai_interaction_llm._load_doc_chunk_text",
        return_value=staff_txt,
    ):
        reply = personnel_single_subject_reply_from_prefetch(
            prefetch,
            user_query="可比公司A2025年员工数量、专业构成及教育程度",
            tenant_id="tenant1",
            fixtures={},
        )
    assert reply
    assert "946" in reply
    assert "242" in reply
    assert "可比公司A" in reply


def test_personnel_fanout_merges_subquery_results():
    from typing import Any

    from backend.services.kb_ask_mcp_reply import personnel_structure_ask_results

    calls: list[str] = []

    def fake_ask(q: str) -> dict[str, Any]:
        calls.append(q)
        if "可比公司A" in q and "研发人员" in q:
            return {
                "reply": "hit",
                "citations": [{"doc_id": "ud_a", "chunk_id": "c1", "chunk_seq_no": 1}],
            }
        if "YYCQ" in q and ("1.1信息-人员" in q or "研发人员" in q):
            return {
                "reply": "hit2",
                "citations": [{"doc_id": "ud_b", "chunk_id": "c2", "chunk_seq_no": 2}],
            }
        return {"reply": "miss", "citations": []}

    merged = personnel_structure_ask_results(
        fake_ask,
        "对比分析YYCQ和可比公司A25年的人员结构",
        max_subqueries=6,
    )
    assert len(merged.get("citations") or []) >= 2
    assert any("研发人员" in c for c in calls)
    assert not any("sec-04" in c for c in calls)


def test_draft_accumulator_skips_duplicate_emit_on_empty_push():
    from backend.services.hermes_stream_sanitize import HermesDraftTraceAccumulator

    acc = HermesDraftTraceAccumulator()
    first = acc.push("### 对比分析\n| 公司 | 人数 |\n| 可比公司A | 3138 |")
    second = acc.push("")
    assert first is not None
    assert second is None
