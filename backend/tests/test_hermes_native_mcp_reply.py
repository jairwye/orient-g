"""Hermes 原生 MCP v2：agent_payload + 成稿契约。"""

from __future__ import annotations

import re
import time
from unittest.mock import patch

import jwt
import pytest

from backend.config import settings

from backend.services.kb_ask_mcp_agent_native import (
    build_agent_payload,
    build_hermes_agent_mcp_reply,
    detect_kb_task_type,
    extract_excerpt_metrics,
)
from backend.tests.test_acl_folder_shared_docs import FOLDER_JINGPIN_CAIBAO_25

PERSONNEL_QUERY = "对比分析YYCQ和可比公司A25年的人员结构"


def _jwt(sub: str = "finance_test") -> str:
    return jwt.encode(
        {"sub": sub, "iat": int(time.time()), "exp": int(time.time()) + 3600},
        settings.auth_secret,
        algorithm="HS256",
    )


def test_detect_kb_task_type_personnel_compare():
    assert detect_kb_task_type(PERSONNEL_QUERY) == "personnel_compare"
    assert detect_kb_task_type("可比公司A2025研发人员数量") == "personnel_compare"


def test_hermes_answer_requirements_personnel_forbids_core_metric_template():
    """深度人员横比不得再要求「核心指标表」（会诱导 22.6 倍规模对照）。"""
    from backend.services.agent_hermes_tier_policy import hermes_answer_requirements

    req = hermes_answer_requirements(tier="full", user_query=PERSONNEL_QUERY)
    assert "人员结构对照" in req
    assert "核心指标表" not in req
    assert "22.6" not in req or "禁止" in req


def test_detect_kb_task_type_finance_compare():
    assert detect_kb_task_type("对比YYCQ与可比公司A2025年销售费用率") == "finance_compare"


def test_extract_excerpt_metrics_rd_headcount():
    m = extract_excerpt_metrics("研发人员数量（人） 1,378 占比 43.91%", task_type="personnel_compare")
    assert m.get("rd_headcount") == 1378
    assert m.get("rd_share_pct") == 43.91


def test_build_agent_payload_personnel_compare_sufficient():
    excerpts = [
        {
            "entity": "可比公司A",
            "doc_id": "ud_a",
            "chunk_id": "c1",
            "excerpt": "研发人员数量 1,378 占比 43.91%",
        },
        {
            "entity": "YYCQ",
            "doc_id": "ud_b",
            "chunk_id": "c2",
            "excerpt": "1.1信息-人员 研发 70.00 运营 61.00",
        },
    ]
    payload = build_agent_payload(
        query=PERSONNEL_QUERY,
        excerpts=excerpts,
        citations=[{"doc_id": "ud_a"}, {"doc_id": "ud_b"}],
    )
    assert payload["schema"] == "orientg_kb_ask_v2"
    assert payload["task_type"] == "personnel_compare"
    assert payload["evidence_sufficient"] is True
    assert "YYCQ" in payload["entities"]
    assert "可比公司A" in payload["entities"]
    assert payload["output_contract"]["language"] == "zh-CN"
    sections = payload["output_contract"]["required_sections"]
    assert sections[0] == "### 人员结构对照"
    assert "### 对比分析" in sections
    assert "### 口径说明" in sections
    assert not any("核心指标对照" in s for s in sections)
    assert payload["suggested_queries_if_insufficient"] == []
    assert payload["evidence"][0]["metrics"].get("rd_headcount") == 1378
    # E：证据已足仍须核证轮（单次 MCP ≠ 充分利用）
    assert payload["output_contract"]["next_action"] == "verify_gap_then_write_final"
    assert payload["output_contract"].get("must_verify_before_final") is True
    assert payload["output_contract"].get("min_orientg_kb_ask_calls") == 2
    assert payload.get("verification_queries")
    assert all(q != PERSONNEL_QUERY for q in payload["verification_queries"])


def test_extract_excerpt_metrics_sales_and_ops():
    m = extract_excerpt_metrics(
        "销售人员 946人；运营人员 242人；行政人员 36人",
        task_type="personnel_compare",
    )
    assert m.get("sales_headcount") == 946
    assert m.get("ops_headcount") == 242


def test_build_hermes_agent_mcp_reply_instructs_fill_structure_table():
    excerpts = [
        {
            "entity": "可比公司A",
            "doc_id": "ud_a",
            "excerpt": "研发人员数量 1,378；销售人员 946人；运营人员 242人",
        },
        {
            "entity": "YYCQ",
            "doc_id": "ud_b",
            "excerpt": "1.1信息-人员 研发 70.00 运营 61.00",
        },
    ]
    reply, payload = build_hermes_agent_mcp_reply(
        query=PERSONNEL_QUERY,
        base_reply="已匹配。",
        excerpts=excerpts,
        citations=[{"doc_id": "ud_a"}, {"doc_id": "ud_b"}],
    )
    assert "人员结构对照" in reply
    assert "尚未核证" in reply or "verify_gap_then_write_final" in reply
    assert "verification_queries" in payload or "建议核实" in reply
    assert "946" in reply and "242" in reply
    assert payload["evidence"][0]["metrics"].get("sales_headcount") == 946
    # MCP 预填对照表骨架：Hermes 应抄用硬数字而非自拟规模倍数
    compact = reply.replace(" ", "")
    assert "|研发|1378人|" in compact or "|研发|1378|" in compact
    assert "硬数字参考表" in reply or "请原样采用下列数字" in reply or "成稿骨架" in reply or "参考表硬数字" in reply
    assert "禁止改写为员工总数倍数对照" in reply


def test_personnel_verification_round_allows_write_final():
    """核实轮（非主横比问句）且证据足 → 立即成稿，不再要求第三次。"""
    excerpts = [
        {
            "entity": "YYCQ",
            "doc_id": "ud_b",
            "excerpt": "1.1信息-人员 研发 70.00 运营 61.00",
        },
    ]
    reply, payload = build_hermes_agent_mcp_reply(
        query="YYCQ 2025 1.1信息-人员 研发 运营",
        base_reply="已匹配。",
        excerpts=excerpts
        + [
            {
                "entity": "可比公司A",
                "doc_id": "ud_a",
                "excerpt": "研发人员数量 1,378；销售人员 946人；运营人员 242人",
            }
        ],
        citations=[{"doc_id": "ud_a"}, {"doc_id": "ud_b"}],
    )
    assert payload["output_contract"]["next_action"] == "write_final_answer_now"
    assert "立即用中文写终稿" in reply
    assert "尚未核证" not in reply


def test_build_agent_payload_insufficient_suggests_chinese_queries():
    payload = build_agent_payload(
        query=PERSONNEL_QUERY,
        excerpts=[{"entity": "可比公司A", "doc_id": "ud_a", "excerpt": "研发 1378"}],
        citations=[{"doc_id": "ud_a"}],
    )
    assert payload["evidence_sufficient"] is False
    suggested = payload["suggested_queries_if_insufficient"]
    assert suggested
    assert all(re.search(r"[\u4e00-\u9fff]", q) for q in suggested)
    assert not any("employee structure" in q.lower() for q in suggested)


def test_build_hermes_agent_mcp_reply_includes_json_and_excerpts():
    excerpts = [
        {"entity": "可比公司A", "doc_id": "ud_a", "excerpt": "研发 1,378"},
        {"entity": "YYCQ", "doc_id": "ud_b", "excerpt": "1.1信息-人员 70"},
    ]
    reply, payload = build_hermes_agent_mcp_reply(
        query=PERSONNEL_QUERY,
        base_reply="已在权限范围内匹配。",
        excerpts=excerpts,
        citations=[{"doc_id": "ud_a"}, {"doc_id": "ud_b"}],
    )
    assert "orientg_kb_ask_v2" in reply
    assert "证据已足" in reply
    assert "尚未核证" in reply or payload["output_contract"]["next_action"] == "verify_gap_then_write_final"
    assert "人员结构证据节选" in reply
    assert "1,378" in reply
    assert payload["evidence_sufficient"] is True


@patch("backend.services.knowledge_pipeline.ask_knowledge")
def test_orientg_kb_ask_native_mode_returns_agent_payload(mock_ask, monkeypatch):
    from backend.config import settings
    from backend.services import orientg_mcp_tools as tools
    from backend.services.hermes_client import _register_session

    monkeypatch.setattr(settings, "hermes_native_mcp_reply", True)
    mock_ask.return_value = {
        "reply": "混合检索命中 2 条证据。",
        "citations": [
            {"doc_id": "ud_a", "chunk_id": "c1"},
            {"doc_id": "ud_b", "chunk_id": "c2"},
        ],
    }
    with patch(
        "backend.services.kb_ask_mcp_reply.build_personnel_compare_excerpts",
        return_value=[
            {"entity": "可比公司A", "doc_id": "ud_a", "chunk_id": "c1", "excerpt": "研发 1378"},
            {"entity": "YYCQ", "doc_id": "ud_b", "chunk_id": "c2", "excerpt": "1.1信息-人员 70"},
        ],
    ):
        tok = _jwt()
        sk = _register_session(
            tok,
            "s_mcp_native",
            username="finance_test",
            orientg_chat_session_id="s_mcp_native",
            kb_scope={"selected_folder_ids": [FOLDER_JINGPIN_CAIBAO_25]},
            orientg_route="hermes_full",
        )
        out = tools.orientg_kb_ask(tok, PERSONNEL_QUERY, hermes_session_key=sk)
    assert out.get("ok") is True
    payload = out.get("agent_payload") or {}
    assert payload.get("schema") == "orientg_kb_ask_v2"
    assert "orientg_kb_ask_v2" in str(out.get("reply") or "")
    assert out.get("evidence_excerpts")


def test_native_primer_does_not_forbid_using_mcp_evidence():
    from backend.services.hermes_kb_mcp_bridge import format_kb_ask_primer_for_instructions

    text = format_kb_ask_primer_for_instructions(
        query=PERSONNEL_QUERY,
        reply="YYCQ 研发 70",
        citations=[{"doc_id": "ud_x"}],
        native_mode=True,
    )
    assert "不得" not in text or "不可替代" not in text
    assert "agent_payload" in text or "Hermes MCP" in text


def test_kb_ask_tool_invocation_hint_native_mode():
    from backend.services.hermes_kb_mcp_bridge import kb_ask_tool_invocation_hint

    hint = kb_ask_tool_invocation_hint(
        session_key="sk1",
        user_query=PERSONNEL_QUERY,
        native_mode=True,
    )
    assert "agent_payload" in hint.get("instruction") or "v2" in hint.get("instruction", "")
    assert "写终稿" in hint.get("instruction", "")


def test_hermes_native_personnel_reply_sufficient_good_draft():
    from backend.services.kb_ask_mcp_agent_native import hermes_native_personnel_reply_sufficient

    good = (
        "## 人员结构对照\n"
        "| 指标 | YYCQ | 可比公司A |\n"
        "| --- | --- | --- |\n"
        "| 研发 | 70 | 1,378 |\n"
        "| 运营 | 61 | 946 |\n\n"
        "### 对比分析\n"
        "YYCQ以 Excel 1.1信息-人员 为主，研发约 70 人；可比公司A年报披露研发人员 1,378 人，"
        "销售与运营分项见专业构成表。两家披露口径不同，横比时须注意年报 section 与 Excel 切块差异。\n"
        "### 口径说明\nYYCQ为内部 Excel；可比公司A为公开发行年报员工章节。\n"
    )
    assert hermes_native_personnel_reply_sufficient(
        good,
        user_query=PERSONNEL_QUERY,
        hermes_kb_ask_count=2,
    )


def test_hermes_native_personnel_reply_sufficient_rejects_planning():
    from backend.services.kb_ask_mcp_agent_native import hermes_native_personnel_reply_sufficient

    assert not hermes_native_personnel_reply_sufficient(
        "Let me search the knowledge base for employee structure.",
        user_query=PERSONNEL_QUERY,
        hermes_kb_ask_count=2,
    )


def test_hermes_native_personnel_reply_sufficient_rejects_scale_multiple_template():
    """22.6 倍 / 核心指标规模对照：不得标 sufficient（否则 gate/误归因会整页模板覆盖）。"""
    from backend.services.kb_ask_mcp_agent_native import hermes_native_personnel_reply_sufficient

    bad = (
        "##一、总体规模对比\n"
        "|指标|可比公司A|YYCQ|差距倍数|\n"
        "|在职员工总数|3,138人|139人|22.6倍|\n"
        "###二、专业构成对比\n研发 1,066 / YYCQ 95；销售人员 946；运营 242；70人。\n"
        "YYCQ与可比公司A对比分析。\n"
    )
    assert not hermes_native_personnel_reply_sufficient(
        bad,
        user_query=PERSONNEL_QUERY,
        hermes_kb_ask_count=1,
    )


def test_hermes_native_personnel_reply_sufficient_rejects_incomplete_sanqi_table():
    """不完整对照表：仍可 skip 补检索；但 classify 不得标为可接受终稿；gate 另测。"""
    from backend.services.kb_ask_mcp_agent_native import hermes_native_personnel_reply_sufficient
    from backend.services.hermes_response_analysis import classify_hermes_response

    incomplete = (
        "## YYCQ vs 可比公司A · 2025 人员结构对比\n\n"
        "### 人员结构对照\n\n"
        "| 职能归属 | 可比公司A | YYCQ |\n"
        "| 研发 | 1378 人 | 70 人 |\n"
        "| 销售 | 证据未覆盖（节选无该分项） | 证据未覆盖 |\n\n"
        "### 对比分析\n\n- 运营与销售口径不同，须以年报分项为准。\n"
    )
    assert hermes_native_personnel_reply_sufficient(
        incomplete,
        user_query=PERSONNEL_QUERY,
        hermes_kb_ask_count=1,
    )
    c = classify_hermes_response(incomplete, user_query=PERSONNEL_QUERY)
    assert c["acceptable_personnel_final"] is False


def test_hermes_native_sufficient_accepts_planning_prefixed_evidence():
    """Live P1：Hermes 过程稿常带规划话术 + 硬数字，应 skip 补检索交 gate 成稿。"""
    from backend.services.kb_ask_mcp_agent_native import hermes_native_personnel_reply_sufficient

    draft = (
        "我需要基于知识库证据来对比分析这两家公司2025年的人员结构。"
        "Evidence Pack中已有一些数据，但我需要进一步检索。先做补检索。\n"
        "现在我已获取了足够的证据数据。让我基于所有证据撰写终稿。"
        "可比公司A：总员工3138人，销售人员946人，运营人员242人，研发人员1378人；"
        "YYCQ：研发70人，运营61人。两家口径不同不可直接比规模。"
    )
    assert hermes_native_personnel_reply_sufficient(
        draft,
        user_query=PERSONNEL_QUERY,
        hermes_kb_ask_count=1,
    )


def test_structured_gate_keeps_hermes_when_native_acceptable_even_if_incomplete(monkeypatch):
    """目标3：native 下合格/近似合格 Hermes 稿不得被 incomplete 表触发整页 gate 覆盖。"""
    from backend.config import settings
    from backend.services.agent_kb_supplemental import apply_personnel_structured_final_gate

    monkeypatch.setattr(settings, "hermes_native_mcp_reply", True)
    monkeypatch.setattr(settings, "hermes_native_skip_supplemental", True)
    hermes_draft = (
        "## YYCQ与可比公司A 2025 人员结构（Hermes 主写）\n\n"
        "### 人员结构对照\n\n"
        "| 职能归属 | 可比公司A | YYCQ |\n"
        "| --- | --- | --- |\n"
        "| 研发 | 1378 人 | 70 人 |\n"
        "| 销售 | 证据未覆盖（节选无该分项） | 证据未覆盖 |\n"
        "| 运营 | 242 人 | 61 人 |\n\n"
        "### 对比分析\n\n"
        "- 结构差异明显：可比公司A销售 946、运营 242；YYCQ以 Excel 四分项为主。\n"
        "- 口径不同不可直接比规模。\n"
        "### 口径说明\n见年报与 1.1信息-人员。\n"
    )
    template = (
        "## YYCQ vs 可比公司A · 2025 人员结构对比\n\n"
        "**结论**：以下按**职能归属/人员分项**对比 2025 年人员结构；\n"
        "### 人员结构对照\n| 销售 | 946 人 | 证据未覆盖 |\n"
        "以上数据均来自当前知识库 citations 节选\n"
    )
    with patch(
        "backend.services.kb_ask_mcp_reply.personnel_compare_reply_from_prefetch",
        return_value=template,
    ):
        out, applied = apply_personnel_structured_final_gate(
            hermes_draft,
            prefetch_result={"ok": True, "evidence_pack": {"task_type": "compare"}},
            user_query=PERSONNEL_QUERY,
            tenant_id="tenant1",
        )
    assert applied is False
    assert out == hermes_draft
    assert "Hermes 主写" in out
    assert "以上数据均来自当前知识库 citations 节选" not in out


def test_structured_gate_native_keeps_hermes_analysis_prose_with_anchors(monkeypatch):
    """native：有分析+硬锚点但无对照表时，structured gate 不得换 Orient-G 模板（交 coerce）。"""
    from backend.config import settings
    from backend.services.agent_kb_supplemental import apply_personnel_structured_final_gate

    monkeypatch.setattr(settings, "hermes_native_mcp_reply", True)
    monkeypatch.setattr(settings, "hermes_native_skip_supplemental", True)
    hermes = (
        "可比公司A销售946人、运营242人、研发1378人；YYCQ研发70、运营61。"
        "结构差异明显：两家披露口径不同，不可直接比员工总数。"
        "对比分析：可比公司A销售职能突出，YYCQ以 excel 四分项为主。"
    )
    template = (
        "## YYCQ vs 可比公司A · 2025 人员结构对比\n"
        "**结论**：以下按**职能归属/人员分项**\n"
        "### 人员结构对照\n| 销售 | 946 | 证据未覆盖 |\n"
        "以上数据均来自当前知识库 citations 节选\n"
    )
    with patch(
        "backend.services.kb_ask_mcp_reply.personnel_compare_reply_from_prefetch",
        return_value=template,
    ):
        out, applied = apply_personnel_structured_final_gate(
            hermes,
            prefetch_result={"ok": True, "evidence_pack": {"task_type": "compare"}},
            user_query=PERSONNEL_QUERY,
            tenant_id="tenant1",
        )
    assert applied is False
    assert out == hermes


def test_structured_gate_still_fuses_excerpt_dump_in_native(monkeypatch):
    """保险丝：excerpt dump 在 native 下用 MCP 骨架纠偏，禁止 Orient-G 模板。"""
    from backend.config import settings
    from backend.services.agent_kb_supplemental import apply_personnel_structured_final_gate
    from backend.services.personnel_compare_report import looks_like_orientg_personnel_template

    monkeypatch.setattr(settings, "hermes_native_mcp_reply", True)
    monkeypatch.setattr(settings, "hermes_native_skip_supplemental", True)
    dump = (
        "以下对比基于知识库检索结果。\n"
        "doc_id: ud_a\n---\n连带责任保证\n营业收入合计\n"
        "doc_id: ud_b\n---\n货币资金\n对比说明：证据未整理。\n"
    )
    template = (
        "## YYCQ vs 可比公司A · 2025 人员结构对比\n\n"
        "### 人员结构对照\n| 研发 | 1378 | 70 |\n"
        "### 对比分析\n- 结构差异\n"
        "以上数据均来自当前知识库 citations 节选\n"
    )
    prefetch = {
        "ok": True,
        "evidence_pack": {"task_type": "compare"},
        "evidence_excerpts": [
            {
                "entity": "可比公司A",
                "doc_id": "ud_a",
                "excerpt": "研发人员数量 1378；销售人员 946人；运营人员 242人",
            },
            {
                "entity": "YYCQ",
                "doc_id": "ud_b",
                "excerpt": "1.1信息-人员 研发 70.00 运营 61.00",
            },
        ],
        "citations": [{"doc_id": "ud_a"}, {"doc_id": "ud_b"}],
    }
    with patch(
        "backend.services.kb_ask_mcp_reply.personnel_compare_reply_from_prefetch",
        return_value=template,
    ):
        out, applied = apply_personnel_structured_final_gate(
            dump,
            prefetch_result=prefetch,
            user_query=PERSONNEL_QUERY,
            tenant_id="tenant1",
        )
    assert applied is False
    assert "人员结构对照" in out
    assert not looks_like_orientg_personnel_template(out)


def test_looks_like_orientg_personnel_template():
    from backend.services.personnel_compare_report import looks_like_orientg_personnel_template

    assert looks_like_orientg_personnel_template(
        "## YYCQ vs 可比公司A · 2025 人员结构对比\n"
        "**结论**：以下按**职能归属/人员分项**对比 2025 年人员结构；\n"
        "以上数据均来自当前知识库 citations 节选\n"
    )
    assert not looks_like_orientg_personnel_template(
        "## YYCQ与可比公司A 2025 人员结构（Hermes）\n"
        "### 人员结构对照\n| 研发 | 1378 | 70 |\n### 对比分析\n- ok\n"
    )


def test_coerce_hermes_personnel_to_mcp_skeleton_when_scale_narrative(monkeypatch):
    """native：Hermes 写规模对照时，用 MCP 骨架纠偏（非 Orient-G 模板指纹），出处仍 Hermes。"""
    from backend.config import settings
    from backend.services.agent_kb_supplemental import (
        apply_hermes_mcp_personnel_contract_coerce,
        resolve_personnel_reply_source,
    )

    monkeypatch.setattr(settings, "hermes_native_mcp_reply", True)
    monkeypatch.setattr(settings, "hermes_native_skip_supplemental", True)
    bad = (
        "### 核心指标对照\n|指标|可比公司A|YYCQ|\n|员工总数|3138|139|22.6倍|\n"
        "研发 1066；销售 946；YYCQ 70。\n"
    )
    prefetch = {
        "ok": True,
        "evidence_excerpts": [
            {
                "entity": "可比公司A",
                "doc_id": "ud_a",
                "excerpt": "研发人员数量 1378；销售人员 946人；运营人员 242人",
            },
            {
                "entity": "YYCQ",
                "doc_id": "ud_b",
                "excerpt": "1.1信息-人员 研发 70.00 运营 61.00",
            },
        ],
        "citations": [{"doc_id": "ud_a"}, {"doc_id": "ud_b"}],
    }
    out, coerced = apply_hermes_mcp_personnel_contract_coerce(
        bad,
        prefetch_result=prefetch,
        user_query=PERSONNEL_QUERY,
        hermes_kb_ask_count=1,
    )
    assert coerced is True
    assert "人员结构对照" in out
    assert "1378" in out and "946" in out
    assert "成稿骨架" not in out
    assert "请原样采用下列数字" not in out
    assert "以上数据均来自当前知识库 citations 节选" not in out
    meta = resolve_personnel_reply_source(
        structured_gate_applied=False,
        misattribution_gate_applied=False,
        reply=out,
    )
    assert meta["reply_source"] == "hermes"


def test_coerce_总体规模_错稿_even_with_empty_prefetch(monkeypatch):
    """宽尺子：CDP 实测「一、总体规模」错稿在 slim prefetch 空节选时仍须纠偏。"""
    from backend.config import settings
    from backend.services.agent_kb_supplemental import apply_hermes_mcp_personnel_contract_coerce

    monkeypatch.setattr(settings, "hermes_native_mcp_reply", True)
    monkeypatch.setattr(settings, "hermes_native_skip_supplemental", True)
    bad = (
        "YYCQ vs 可比公司A 2025年人员结构对比分析\n"
        "一、总体规模与业务定位差异\n"
        "在职员工总数\t3,138人\t139人\n"
        "研发人员（年报口径）\t1,378人\t95人（期末）\n"
        "销售人员\t946人\t10人\n"
        "运营人员\t242人\t61人\n"
        "销售团队极精简，可能依赖渠道分发\n"
    )
    out, coerced = apply_hermes_mcp_personnel_contract_coerce(
        bad,
        prefetch_result={"ok": True, "evidence_excerpts": [], "citations": []},
        user_query=PERSONNEL_QUERY,
        hermes_kb_ask_count=1,
    )
    assert coerced is True
    assert "人员结构对照" in out
    assert "1378" in out or "1,378" in out
    assert "70" in out
    assert "成稿骨架" not in out
    assert "总体规模" not in out
    assert "95人" not in out
    assert "可能依赖" not in out


def test_misattribution_gate_keeps_native_hermes_when_structure_table_ok(monkeypatch):
    """native：已有正确人员结构对照+锚点时，误归因保险丝不整页覆盖。"""
    from backend.config import settings
    from backend.services.agent_kb_supplemental import apply_personnel_misattribution_gate

    monkeypatch.setattr(settings, "hermes_native_mcp_reply", True)
    monkeypatch.setattr(settings, "hermes_native_skip_supplemental", True)
    hermes = (
        "### 人员结构对照\n"
        "| 职能归属 | 可比公司A | YYCQ |\n"
        "| 研发 | 1378 人 | 70 人 |\n"
        "| 销售 | 946 人 | 证据未覆盖 |\n"
        "| 运营 | 242 人 | 61 人 |\n"
        "### 对比分析\n"
        "- 结构差异；注：曾有材料提到规模 139 人勿与分项混比。\n"
        "### 口径说明\n年报 vs excel。\n"
    )
    template = (
        "## YYCQ vs 可比公司A · 2025 人员结构对比\n"
        "**结论**：以下按**职能归属/人员分项**\n"
        "以上数据均来自当前知识库 citations 节选\n"
    )
    with patch(
        "backend.services.kb_ask_mcp_reply.personnel_compare_reply_from_prefetch",
        return_value=template,
    ):
        out, applied = apply_personnel_misattribution_gate(
            hermes,
            prefetch_result={"ok": True, "citations": [{"doc_id": "d1"}]},
            user_query=PERSONNEL_QUERY,
            tenant_id="tenant1",
        )
    assert applied is False
    assert out == hermes


def test_misattribution_gate_native_never_swaps_orientg_template(monkeypatch):
    """目标3：native 下误归因不得再用 Orient-G structured 整页模板刷终稿。"""
    from backend.config import settings
    from backend.services.agent_kb_supplemental import apply_personnel_misattribution_gate

    monkeypatch.setattr(settings, "hermes_native_mcp_reply", True)
    monkeypatch.setattr(settings, "hermes_native_skip_supplemental", True)
    hermes = (
        "可比公司A：总员工3138人，销售人员946人，运营人员242人，研发人员1378人；"
        "YYCQ：研发70人，运营61人。对比分析两家规模差异显著，但口径不同。"
    )
    template = (
        "## YYCQ vs 可比公司A · 2025 人员结构对比\n"
        "**结论**：以下按**职能归属/人员分项**对比\n"
        "### 人员结构对照\n| 销售 | 946 人 | 证据未覆盖 |\n"
        "以上数据均来自当前知识库 citations 节选，口径见各主体 section 标题。\n"
    )
    with patch(
        "backend.services.kb_ask_mcp_reply.personnel_compare_reply_from_prefetch",
        return_value=template,
    ):
        out, applied = apply_personnel_misattribution_gate(
            hermes,
            prefetch_result={"ok": True, "citations": [{"doc_id": "d1"}]},
            user_query=PERSONNEL_QUERY,
            tenant_id="tenant1",
        )
    assert applied is False
    assert out == hermes
    assert "以上数据均来自当前知识库 citations 节选" not in out


def test_coerce_when_scale_misattributed_no_table_even_without_excerpts(monkeypatch):
    """Live/A3：混写 3138 规模且无对照表；prefetch 仅有 reply/citations 时也须 MCP 骨架纠偏。"""
    from backend.config import settings
    from backend.services.agent_kb_supplemental import apply_hermes_mcp_personnel_contract_coerce
    from backend.services.personnel_compare_report import looks_like_orientg_personnel_template

    monkeypatch.setattr(settings, "hermes_native_mcp_reply", True)
    monkeypatch.setattr(settings, "hermes_native_skip_supplemental", True)
    draft = (
        "我需要基于知识库证据来对比分析这两家公司2025年的人员结构。"
        "现在我已获取了足够的证据数据。让我基于所有证据撰写终稿。"
        "可比公司A：总员工3138人，销售人员946人，运营人员242人，研发人员1378人；"
        "YYCQ：研发70人，运营61人。两家口径不同不可直接比规模。"
    )
    prefetch = {
        "ok": True,
        "reply": (
            "可比公司A 研发人员数量 1378；销售人员 946人；运营人员 242人。"
            "YYCQ 1.1信息-人员 研发 70.00 运营 61.00 管理 33.15 支持 45.85。"
        ),
        "citations": [
            {"doc_id": "ud_a", "title": "可比公司A年报"},
            {"doc_id": "ud_b", "title": "YYCQ人员"},
        ],
    }
    out, coerced = apply_hermes_mcp_personnel_contract_coerce(
        draft,
        prefetch_result=prefetch,
        user_query=PERSONNEL_QUERY,
        hermes_kb_ask_count=2,
    )
    assert coerced is True
    assert "人员结构对照" in out
    assert "1378" in out and "946" in out
    assert "成稿骨架" not in out
    assert "以上数据均来自当前知识库 citations 节选" not in out
    assert not looks_like_orientg_personnel_template(out)


def test_coerce_keeps_good_draft_mentioning_员工总数_口径(monkeypatch):
    """A3 根因：口径说明含「员工总数」不得触发 coerce 覆盖长对照稿。"""
    from backend.config import settings
    from backend.services.agent_kb_supplemental import apply_hermes_mcp_personnel_contract_coerce

    monkeypatch.setattr(settings, "hermes_native_mcp_reply", True)
    monkeypatch.setattr(settings, "hermes_native_skip_supplemental", True)
    good = (
        "YYCQ vs 可比公司A · 2025 人员结构对比\n"
        "结论：不可将YYCQ excel 分项合计与可比公司A员工总数直接比规模。\n"
        "### 人员结构对照\n"
        "| 职能归属 | 可比公司A | YYCQ |\n"
        "| 研发 | 1378 人 | 70 人 |\n"
        "| 销售 | 946 人 | 证据未覆盖 |\n"
        "| 运营 | 242 人 | 61 人 |\n"
        "### 对比分析\n"
        "YYCQ excel 四分项；可比公司A年报研发 1378、销售 946、运营 242。\n"
        "结构差异与可比性说明：口径不同，缺失写证据未覆盖。\n"
        "### 口径说明\n"
        "可比公司A=年报节选；YYCQ=excel「1.1信息-人员」。\n"
    )
    out, coerced = apply_hermes_mcp_personnel_contract_coerce(
        good,
        prefetch_result={"ok": True, "evidence_excerpts": [], "citations": []},
        user_query=PERSONNEL_QUERY,
        hermes_kb_ask_count=2,
    )
    assert coerced is False
    assert out == good
    assert "成稿骨架" not in out


def test_resolve_prefers_long_draft_over_skeleton_evt():
    from backend.services.hermes_stream_sanitize import (
        HermesDraftTraceAccumulator,
        resolve_hermes_effective_reply,
    )

    long_draft = (
        "### 人员结构对照\n| 职能 | 可比公司A | YYCQ |\n"
        "| 研发 | 1378 人 | 70 人 |\n| 销售 | 946 人 | 证据未覆盖 |\n"
        "| 运营 | 242 人 | 61 人 |\n### 对比分析\n"
        "两家口径不同；研发可比；可比公司A销售 946、运营 242。\n### 口径说明\n年报 vs excel。\n"
    )
    skeleton = (
        "## 成稿骨架（请原样采用下列数字写入终稿；禁止改写为员工总数倍数对照）\n"
        "### 人员结构对照\n| 职能归属 | 可比公司A | YYCQ |\n"
        "| 研发 | 1378 人 | 70 人 |\n"
    )
    acc = HermesDraftTraceAccumulator()
    acc.push(long_draft)
    out = resolve_hermes_effective_reply(
        evt_reply=skeleton,
        draft_acc=acc,
        user_query=PERSONNEL_QUERY,
    )
    assert "成稿骨架" not in out
    assert "946" in out
    assert len(out) > len(skeleton)


def test_resolve_personnel_reply_source_hermes_when_gates_off():
    from backend.services.agent_kb_supplemental import resolve_personnel_reply_source

    meta = resolve_personnel_reply_source(
        structured_gate_applied=False,
        misattribution_gate_applied=False,
        supplemental_ran=False,
        supplemental_adopted=False,
        reply="### 人员结构对照\n| 研发 | 1378 | 70 |\n",
    )
    assert meta["reply_source"] == "hermes"
    assert meta["structured_gate_applied"] is False


def test_resolve_personnel_reply_source_gate_when_applied():
    from backend.services.agent_kb_supplemental import resolve_personnel_reply_source

    meta = resolve_personnel_reply_source(
        structured_gate_applied=True,
        misattribution_gate_applied=False,
        supplemental_ran=False,
        supplemental_adopted=False,
        reply="以上数据均来自当前知识库 citations 节选",
    )
    assert meta["reply_source"] == "orientg_structured_gate"
    assert meta["structured_gate_applied"] is True


def test_needs_supplemental_skipped_when_native_hermes_sufficient(monkeypatch):
    from backend.config import settings
    from backend.services.agent_kb_router import AgentRoute
    from backend.services.agent_kb_supplemental import needs_hermes_supplemental

    monkeypatch.setattr(settings, "hermes_native_mcp_reply", True)
    monkeypatch.setattr(settings, "hermes_native_skip_supplemental", True)
    good = (
        "## 人员结构对照\n| 指标 | YYCQ | 可比公司A |\n| --- | --- | --- |\n"
        "| 研发 | 70 | 1,378 |\n| 运营 | 61 | 946 |\n"
        "### 对比分析\n"
        "结构差异明显：YYCQ Excel 1.1信息-人员 研发约 70、运营 61；"
        "可比公司A年报研发 1,378 人，销售与运营见专业构成表。横比须注意披露口径差异。\n"
        "### 口径说明\n见各主体披露章节。\n"
    )
    prefetch = {
        "ok": True,
        "citations": [{"doc_id": "d1"}],
        "evidence_pack": {"task_type": "compare", "gaps": []},
    }
    assert not needs_hermes_supplemental(
        agent_route=AgentRoute.hermes_full,
        prefetch_result=prefetch,
        hermes_kb_ask_count=2,
        hermes_reply=good,
        user_query=PERSONNEL_QUERY,
    )
