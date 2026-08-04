"""人员结构浏览器实测矩阵 TDD（用例定义 + validate + supplemental 集成）。"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend" / "scripts"))

from finance_matrix_personnel_cases import PERSONNEL_CASE_SPECS, PERSONNEL_MATRIX  # noqa: E402
from finance_matrix_personnel_validate import (  # noqa: E402
    BROWSER_FAIL_HERMES_V1,
    BROWSER_FAIL_HERMES_V2,
    GOOD_PERSONNEL_COMPARE_EXCERPT,
    PERSONNEL_COMPARE_QUERY,
    personnel_case_kind,
    personnel_compare_answer_ok,
    personnel_single_answer_ok,
)
from finance_matrix_browser_validate import validate_row  # noqa: E402


def _row(query: str, head: str, *, mode: str = "deep", subject: str = "A3-横比-深度", honest: bool = False) -> dict:
    tier = {
        "fast": "执行过程(Tier 0（本地证据综合） · 快速（Orient-G 本地证据综合，未走 Hermes）)",
        "standard": "执行过程(Tier 1（Hermes 受限） · 标准（Hermes lite + Evidence Pack）)",
        "deep": "执行过程(Tier 2（Hermes 深度） · 深度（Hermes 全编排）)",
    }[mode]
    return {
        "category": "personnel",
        "subject": subject,
        "mode": mode,
        "query": query,
        "tier_line": tier,
        "citations": 12,
        "streamDone": True,
        "orientg_kb_ask_calls": 3,
        "notes": "tdd",
        "extract": {
            "hasMoney": False,
            "honestMissing": honest,
            "head": head,
            "len": len(head),
            "streamFail": False,
        },
    }


# --- 用例矩阵定义 ---


def test_personnel_matrix_has_eight_browser_cases_with_specs():
    assert len(PERSONNEL_MATRIX) == 8
    keys = {f"{c}::{s}::{m}" for c, s, m, _ in PERSONNEL_MATRIX}
    assert "personnel::A3-横比-深度::deep" in keys
    assert "personnel::A2-横比-标准::standard" in keys
    assert "personnel::A1-横比-快速::fast" in keys
    assert "personnel::B1-可比公司A-员工专节::fast" in keys
    assert "personnel::C1-YYCQ-excel分项::fast" in keys
    assert "personnel::D1-横比-职能::standard" in keys
    assert len(PERSONNEL_CASE_SPECS) == 8


def test_personnel_case_kind_classification():
    assert personnel_case_kind(PERSONNEL_COMPARE_QUERY) == "compare"
    assert personnel_case_kind("可比公司A2025年公司研发人员情况") == "sanqi_single"
    assert personnel_case_kind("YYCQ2025年1.1信息-人员") == "yycq_single"
    assert personnel_case_kind("对比YYCQ与可比公司A2025年研发人员数量") == "compare"


def test_query_wants_personnel_compare():
    from backend.services.kb_retrieval_plan import query_wants_personnel_compare

    assert query_wants_personnel_compare(PERSONNEL_COMPARE_QUERY)
    assert not query_wants_personnel_compare("可比公司A2025年公司研发人员情况")


# --- 失败样例（Red）---


@pytest.mark.parametrize(
    "fail_text",
    [BROWSER_FAIL_HERMES_V1, BROWSER_FAIL_HERMES_V2],
)
def test_browser_fail_samples_not_ok(fail_text: str):
    ok, _checks = personnel_compare_answer_ok(fail_text, user_query=PERSONNEL_COMPARE_QUERY, mode="deep", hermes_kb_ask_calls=2)
    assert ok is False
    row = validate_row(_row(PERSONNEL_COMPARE_QUERY, fail_text))
    assert row["ok"] is False


# --- 成功样例（Green）---


def test_good_excerpt_passes_compare_validate():
    ok, checks = personnel_compare_answer_ok(
        GOOD_PERSONNEL_COMPARE_EXCERPT,
        user_query=PERSONNEL_COMPARE_QUERY,
        mode="deep",
        hermes_kb_ask_calls=3,
    )
    assert ok is True
    assert checks.get("sanqi_roles_in_table_ok")
    row = _row(PERSONNEL_COMPARE_QUERY, GOOD_PERSONNEL_COMPARE_EXCERPT, subject="A3-横比-深度")
    row["reply_source"] = "hermes"
    row["structured_gate_applied"] = False
    row["kb_supplemental"] = False
    row["hermes_kb_ask_calls"] = 2
    row["gateway_kb_ask_calls"] = 1
    row["hermes_mcp_retry_count"] = 0
    assert validate_row(row)["ok"] is True


def test_a3_deep_rejects_orientg_template_authorship():
    """目标3 anti-gate：Orient-G 模板套话不得刷绿 A3。"""
    from backend.services.personnel_compare_report import format_personnel_compare_structured_report

    template = format_personnel_compare_structured_report(
        [
            {
                "entity": "可比公司A",
                "excerpt": "研发人员数量 1378 占比43.91%；销售人员 946人；运营人员 242人；行政人员 36人",
            },
            {
                "entity": "YYCQ",
                "excerpt": "1.1信息-人员\n| 运营 | 61 |\n| 管理 | 33.15 |\n| 研发 | 70 |\n| 支持 | 45.85 |\n",
            },
        ],
        user_query=PERSONNEL_COMPARE_QUERY,
    )
    assert template
    row = _row(PERSONNEL_COMPARE_QUERY, template, subject="A3-横比-深度")
    row["reply_source"] = "orientg_structured_gate"
    row["structured_gate_applied"] = True
    out = validate_row(row)
    assert out["ok"] is False
    assert out.get("checks", {}).get("hermes_authorship_ok") is False
    assert out.get("checks", {}).get("orientg_template_fingerprint") is True


def test_a3_deep_accepts_hermes_authored_non_template():
    hermes = (
        "## YYCQ与可比公司A 2025 人员结构\n\n"
        "### 人员结构对照\n\n"
        "| 职能归属 | 可比公司A | YYCQ |\n"
        "| --- | --- | --- |\n"
        "| 研发 | 1378 人 | 70 人 |\n"
        "| 运营 | 242 人 | 61 人 |\n"
        "| 管理 | 36 人 | 33 人 |\n"
        "| 支持 | 312 人 | 46 人 |\n"
        "| 销售 | 946 人 | 证据未覆盖 |\n\n"
        "### 对比分析\n\n"
        "- 结构差异明显，职能分项口径不可直接比规模。\n"
        "### 口径说明\n年报 vs excel。\n"
    )
    row = _row(PERSONNEL_COMPARE_QUERY, hermes, subject="A3-横比-深度")
    row["reply_source"] = "hermes"
    row["structured_gate_applied"] = False
    row["kb_supplemental"] = False
    row["hermes_kb_ask_calls"] = 2
    row["gateway_kb_ask_calls"] = 1
    out = validate_row(row)
    assert out["ok"] is True
    assert out.get("checks", {}).get("hermes_authorship_ok") is True
    assert out.get("checks", {}).get("gateway_prefetch_slim_ok") is True
    assert out.get("checks", {}).get("hermes_mcp_self_ok") is True


def test_a3_rejects_single_hermes_mcp_call():
    """E：hermes×1（一次取证即停）不得刷绿 A3。"""
    row = _row(PERSONNEL_COMPARE_QUERY, GOOD_PERSONNEL_COMPARE_EXCERPT, subject="A3-横比-深度")
    row["reply_source"] = "hermes"
    row["structured_gate_applied"] = False
    row["kb_supplemental"] = False
    row["hermes_kb_ask_calls"] = 1
    row["gateway_kb_ask_calls"] = 1
    row["hermes_mcp_retry_count"] = 0
    out = validate_row(row)
    assert out["ok"] is False
    assert out.get("checks", {}).get("hermes_mcp_self_ok") is False


def test_a3_rejects_high_gateway_prefetch():
    """目标 4：A3 gateway×9 不得刷绿。"""
    hermes = (
        "## YYCQ与可比公司A 2025 人员结构\n\n"
        "### 人员结构对照\n\n"
        "| 职能归属 | 可比公司A | YYCQ |\n"
        "| --- | --- | --- |\n"
        "| 研发 | 1378 人 | 70 人 |\n"
        "| 运营 | 242 人 | 61 人 |\n"
        "| 管理 | 36 人 | 33 人 |\n"
        "| 支持 | 312 人 | 46 人 |\n"
        "| 销售 | 946 人 | 证据未覆盖 |\n\n"
        "### 对比分析\n结构差异。\n"
    )
    row = _row(PERSONNEL_COMPARE_QUERY, hermes, subject="A3-横比-深度")
    row["reply_source"] = "hermes"
    row["structured_gate_applied"] = False
    row["kb_supplemental"] = False
    row["hermes_kb_ask_calls"] = 2
    row["gateway_kb_ask_calls"] = 9
    out = validate_row(row)
    assert out["ok"] is False
    assert out.get("checks", {}).get("gateway_prefetch_slim_ok") is False


def test_a3_rejects_speculation_prose():
    """宽尺子 C：主气泡含推算/推断不得刷绿 A3。"""
    hermes = (
        "## YYCQ与可比公司A 2025 人员结构\n\n"
        "### 人员结构对照\n\n"
        "| 职能归属 | 可比公司A | YYCQ |\n"
        "| --- | --- | --- |\n"
        "| 研发 | 1378 人 | 70 人 |\n"
        "| 运营 | 242 人 | 61 人 |\n"
        "| 管理 | 36 人 | 33 人 |\n"
        "| 支持 | 312 人 | 46 人 |\n"
        "| 销售 | 946 人 | 证据未覆盖 |\n\n"
        "### 对比分析\n根据推算，可比公司A销售规模更大；可推断YYCQ为研发驱动。\n"
    )
    row = _row(PERSONNEL_COMPARE_QUERY, hermes, subject="A3-横比-深度")
    row["reply_source"] = "hermes"
    row["structured_gate_applied"] = False
    row["kb_supplemental"] = False
    row["hermes_kb_ask_calls"] = 2
    row["gateway_kb_ask_calls"] = 1
    row["hermes_mcp_retry_count"] = 0
    out = validate_row(row)
    assert out["ok"] is False
    assert "unsupported_speculation" in (out.get("checks", {}).get("forbidden_leaks") or [])


def test_a3_rejects_forced_mcp_retry():
    """宽尺子 B：强制 MCP 重试不得作为 A3 常态绿。"""
    hermes = GOOD_PERSONNEL_COMPARE_EXCERPT
    row = _row(PERSONNEL_COMPARE_QUERY, hermes, subject="A3-横比-深度")
    row["reply_source"] = "hermes"
    row["structured_gate_applied"] = False
    row["kb_supplemental"] = False
    row["hermes_kb_ask_calls"] = 2
    row["gateway_kb_ask_calls"] = 1
    row["hermes_mcp_retry_count"] = 1
    out = validate_row(row)
    assert out["ok"] is False
    assert out.get("checks", {}).get("hermes_mcp_retry_ok") is False


def test_a3_accepts_zero_retry_clean_hermes():
    row = _row(PERSONNEL_COMPARE_QUERY, GOOD_PERSONNEL_COMPARE_EXCERPT, subject="A3-横比-深度")
    row["reply_source"] = "hermes"
    row["structured_gate_applied"] = False
    row["kb_supplemental"] = False
    row["hermes_kb_ask_calls"] = 2
    row["gateway_kb_ask_calls"] = 1
    row["hermes_mcp_retry_count"] = 0
    out = validate_row(row)
    assert out["ok"] is True, out.get("checks")
    assert out.get("checks", {}).get("hermes_mcp_retry_ok") is True
    assert out.get("checks", {}).get("hermes_mcp_self_ok") is True


def test_a3_accepts_hermes_tab_table_with_role_suffix():
    """浏览器 DOM 常见：人员结构对照 +「研发人员\\t…」非管道表。"""
    hermes = (
        "根据知识库证据，以下是YYCQ与可比公司A2025年人员结构的对比分析：\n"
        "##人员结构对照\n"
        "职能归属\t可比公司A\tYYCQ\n"
        "研发人员\t1,378人（占比43.91%）\t70人\n"
        "销售人员\t946人\t证据未覆盖\n"
        "运营人员\t242人\t61人\n"
        "管理人员\t36人\t33.15人\n"
        "支持人员\t115人\t45.85人\n"
        "对比分析：结构差异明显，口径不同不可直接比规模。\n"
        "规模旁白：可比公司A员工总数3,138人，不可与分项混比。\n"
    )
    from backend.scripts.finance_matrix_personnel_validate import personnel_compare_has_core_table

    assert personnel_compare_has_core_table(hermes) is True
    row = _row(PERSONNEL_COMPARE_QUERY, hermes, subject="A3-横比-深度")
    row["reply_source"] = "hermes"
    row["structured_gate_applied"] = False
    row["kb_supplemental"] = False
    row["hermes_kb_ask_calls"] = 2
    row["gateway_kb_ask_calls"] = 1
    row["hermes_mcp_retry_count"] = 0
    out = validate_row(row)
    assert out["ok"] is True, out.get("checks")


def test_compare_anchors_all_required():
    partial = "### 可比公司A\n研发 1,378\n### YYCQ\n缺少分项"
    ok, _checks = personnel_compare_answer_ok(partial, user_query=PERSONNEL_COMPARE_QUERY, mode="fast")
    assert ok is False


# --- 三档横比 validate（mode tier 线）---


@pytest.mark.parametrize(
    "mode,subject",
    [("deep", "A3-横比-深度"), ("standard", "A2-横比-标准"), ("fast", "A1-横比-快速")],
)
def test_compare_passes_all_tiers(mode: str, subject: str):
    row = _row(PERSONNEL_COMPARE_QUERY, GOOD_PERSONNEL_COMPARE_EXCERPT, mode=mode, subject=subject)
    if subject.startswith("A3"):
        row["reply_source"] = "hermes"
        row["structured_gate_applied"] = False
        row["kb_supplemental"] = False
        row["hermes_kb_ask_calls"] = 2
        row["gateway_kb_ask_calls"] = 1
        row["hermes_mcp_retry_count"] = 0
    assert validate_row(row)["ok"] is True


# --- 单主体用例 ---


def test_sanqi_single_pass():
    body = "## 公司研发人员情况\n可比公司A 研发人员数量 1,378 占比 43.91%"
    assert personnel_single_answer_ok(body, kind="sanqi_single")
    row = validate_row(_row("可比公司A2025年研发人员情况", body, mode="fast", subject="B2-可比公司A-研发专节"))
    assert row["ok"] is True


def test_yycq_single_pass():
    body = "## 1.1信息-人员\nYYCQ 研发 70.00 运营 61.00"
    assert personnel_single_answer_ok(body, kind="yycq_single")
    row = validate_row(_row("YYCQ2025年1.1信息-人员", body, mode="fast", subject="C1-YYCQ-excel分项"))
    assert row["ok"] is True


# --- supplemental 集成：丢 labels 后仍可从 kb_scope 恢复 + 节选成稿 ---

SANQI_TXT = (
    "## 1、员工数量、专业构成及教育程度\n"
    "| 销售人员 | 946 |\n| 运营人员 | 242 |\n"
    "## 公司研发人员情况\n研发人员数量 1,378 占比 43.91%"
)
YYCQ_TXT = "## 1.1信息-人员\n研发 70.00 运营 61.00\n运营 61.00"
UD_37 = "ud_sanqi_personnel_001"
UD_YY = "ud_yycq_personnel_001"
FOLDER_JINGPIN = "f_6f3638e4513f492c9610ddb5dda77c20"


def test_folder_label_25_maps_to_yycq():
    from backend.services.kb_ask_mcp_reply import _entity_from_folder_label

    ents = ["可比公司A", "YYCQ"]
    assert _entity_from_folder_label("ud_x", ents, {"ud_x": "25"}) == "YYCQ"
    assert _entity_from_folder_label("ud_y", ents, {"ud_y": "PeerA25"}) == "可比公司A"


def _chunk_loader(tenant_id: str, doc_id: str, chunk_id: str | None, seq):
    if doc_id == UD_37:
        return SANQI_TXT
    if doc_id == UD_YY:
        return YYCQ_TXT
    return ""


@patch("backend.services.ai_interaction_llm._load_doc_chunk_text", side_effect=_chunk_loader)
def test_personnel_excerpt_from_prefetch_with_folder_labels(_mock_load):
    from backend.services.kb_ask_mcp_reply import personnel_compare_reply_from_prefetch

    prefetch = {
        "ok": True,
        "citations": [
            {"doc_id": UD_37, "chunk_id": "c1"},
            {"doc_id": UD_YY, "chunk_id": "c2"},
        ],
        "evidence_pack": {
            "task_type": "compare",
            "doc_folder_labels": {UD_37: "PeerA25", UD_YY: "25"},
            "multi_company_scope": True,
        },
    }
    out = personnel_compare_reply_from_prefetch(
        prefetch,
        user_query=PERSONNEL_COMPARE_QUERY,
        tenant_id="tenant1",
        fixtures={},
    )
    assert out
    assert "1,378" in out or "1378" in out
    assert "1.1信息-人员" in out
    assert "可比公司A" in out
    assert "YYCQ" in out


@patch("backend.services.ai_interaction_llm._load_doc_chunk_text", side_effect=_chunk_loader)
def test_supplemental_merge_then_pick_excerpt_over_misattributed_synth(_mock_load):
    from backend.services.agent_kb_router import AgentRoute
    from backend.services.agent_kb_supplemental import (
        pick_personnel_compare_final_reply,
        run_supplemental_kb_asks,
    )
    from backend.services.kb_ask_mcp_reply import personnel_compare_reply_from_prefetch

    prefetch = {
        "ok": True,
        "citations": [{"doc_id": UD_37, "chunk_id": "c1"}],
        "evidence_pack": {
            "task_type": "compare",
            "doc_folder_labels": {UD_37: "PeerA25", UD_YY: "25"},
            "multi_company_scope": True,
            "retrieval_queries": [],
        },
    }
    with patch("backend.services.knowledge_pipeline.ask_knowledge") as mock_ask:
        mock_ask.return_value = {
            "ok": True,
            "citations": [{"doc_id": UD_YY, "chunk_id": "c2"}],
            "reply": YYCQ_TXT,
        }
        merged, _tools = run_supplemental_kb_asks(
            user_token="tok",
            user_query=PERSONNEL_COMPARE_QUERY,
            prefetch_result=prefetch,
            kb_scope={"selected_folder_ids": [FOLDER_JINGPIN]},
            attached_doc_ids=None,
            fixtures={"tenant_id": "tenant1"},
            max_queries=1,
        )
    assert merged is not None
    labels = (merged.get("evidence_pack") or {}).get("doc_folder_labels") or {}
    assert labels.get(UD_37) == "PeerA25"
    assert labels.get(UD_YY) == "25"

    excerpt = personnel_compare_reply_from_prefetch(
        merged,
        user_query=PERSONNEL_COMPARE_QUERY,
        tenant_id="tenant1",
        fixtures={"tenant_id": "tenant1"},
        kb_scope={"selected_folder_ids": [FOLDER_JINGPIN]},
    )
    assert excerpt
    final, adopted, reason = pick_personnel_compare_final_reply(
        hermes_reply=BROWSER_FAIL_HERMES_V2,
        synth_reply=BROWSER_FAIL_HERMES_V2,
        excerpt_reply=excerpt,
        user_query=PERSONNEL_COMPARE_QUERY,
        agent_route=AgentRoute.hermes_full,
        prefetch_result=merged,
    )
    assert adopted is True
    assert reason in ("personnel_evidence_excerpt", "personnel_structured_report")
    assert "完全缺失可比公司A" not in final
    assert re.search(r"1378|1,378", final)
    assert "人员结构对照" in final


@patch("backend.services.ai_interaction_llm._load_doc_chunk_text", side_effect=_chunk_loader)
def test_misattribution_gate_after_supplemental(_mock_load, monkeypatch):
    """legacy（非 native）：误归因仍可用 folder 节选纠偏。"""
    from backend.config import settings
    from backend.services.agent_kb_supplemental import apply_personnel_misattribution_gate

    monkeypatch.setattr(settings, "hermes_native_mcp_reply", False)
    monkeypatch.setattr(settings, "hermes_native_skip_supplemental", False)
    prefetch = {
        "ok": True,
        "citations": [
            {"doc_id": UD_37, "chunk_id": "c1"},
            {"doc_id": UD_YY, "chunk_id": "c2"},
        ],
        "evidence_pack": {
            "task_type": "compare",
            "doc_folder_labels": {UD_37: "PeerA25", UD_YY: "25"},
        },
    }
    out, applied = apply_personnel_misattribution_gate(
        BROWSER_FAIL_HERMES_V2,
        prefetch_result=prefetch,
        user_query=PERSONNEL_COMPARE_QUERY,
        tenant_id="tenant1",
        fixtures={"tenant_id": "tenant1"},
        kb_scope={"selected_folder_ids": [FOLDER_JINGPIN]},
    )
    assert applied is True
    assert re.search(r"1378|1,378", out)
    assert "22.6" not in out


@patch("backend.services.ai_interaction_llm._load_doc_chunk_text", side_effect=_chunk_loader)
def test_fast_path_personnel_prefers_excerpt_over_honest_missing_synth(_mock_load):
    from backend.services.agent_kb_fast_path import _apply_personnel_fast_path_reply

    bad_synth = "不确定/缺少证据\n可比公司A数据缺失\nYYCQ数据缺失"
    prefetch = {
        "ok": True,
        "citations": [
            {"doc_id": UD_37, "chunk_id": "c1"},
            {"doc_id": UD_YY, "chunk_id": "c2"},
        ],
        "evidence_pack": {
            "task_type": "compare",
            "doc_folder_labels": {UD_37: "PeerA25", UD_YY: "25"},
        },
    }
    out = _apply_personnel_fast_path_reply(
        synth_reply=bad_synth,
        user_query=PERSONNEL_COMPARE_QUERY,
        prefetch_result=prefetch,
        tenant_id="tenant1",
        fixtures={"tenant_id": "tenant1"},
        kb_scope={"selected_folder_ids": [FOLDER_JINGPIN]},
    )
    assert "1,378" in out or "1378" in out
    assert "1.1信息-人员" in out
    assert "不确定/缺少证据" not in out
