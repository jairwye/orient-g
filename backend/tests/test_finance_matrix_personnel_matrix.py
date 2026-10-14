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
        "| 销售 | 946 人 | 证据未覆盖 |\n"
        "| **分项合计** | — | **210 人**（excel 四项加总） |\n\n"
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
    row["hermes_mcp_retry_count"] = 0
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


def test_a3_rejects_approx_headcount_without_ren_suffix():
    """表内「约210」无「人」后缀亦不得刷绿（CDP 曾漏检）。"""
    hermes = (
        "## 人员结构对照\n\n"
        "| 职能归属 | 可比公司A | YYCQ |\n"
        "| --- | --- | --- |\n"
        "| 研发 | 1,378 | 70 |\n"
        "| 销售 | 946 | 证据未覆盖 |\n"
        "| 运营 | 242 | 61 |\n"
        "| 合计 | 3,138 | 约210 |\n\n"
        "### 对比分析\n结构差异。\n"
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


def test_a3_rejects_kb_supplemental_authorship():
    """禁止 OG recovery/supplemental 冒充 Hermes 主写刷绿。"""
    hermes = (
        "## 人员结构对照\n\n"
        "| 职能归属 | 可比公司A | YYCQ |\n"
        "| --- | --- | --- |\n"
        "| 研发 | 1378 | 70 |\n"
        "| 销售 | 946 | 证据未覆盖 |\n"
        "| 运营 | 242 | 61 |\n\n"
        "### 对比分析\n结构差异。\n"
    )
    row = _row(PERSONNEL_COMPARE_QUERY, hermes, subject="A3-横比-深度")
    row["reply_source"] = "orientg_supplemental"
    row["structured_gate_applied"] = False
    row["kb_supplemental"] = True
    row["hermes_kb_ask_calls"] = 2
    row["gateway_kb_ask_calls"] = 1
    row["hermes_mcp_retry_count"] = 0
    out = validate_row(row)
    assert out["ok"] is False
    assert out.get("checks", {}).get("hermes_authorship_ok") is False


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


def test_a3_rejects_missing_reply_source():
    """手测同路径：reply_source 缺省不得刷绿（禁门禁顶替漏检）。"""
    row = _row(PERSONNEL_COMPARE_QUERY, GOOD_PERSONNEL_COMPARE_EXCERPT, subject="A3-横比-深度")
    row["structured_gate_applied"] = False
    row["kb_supplemental"] = False
    row["hermes_kb_ask_calls"] = 2
    row["gateway_kb_ask_calls"] = 1
    row["hermes_mcp_retry_count"] = 0
    out = validate_row(row)
    assert out["ok"] is False
    assert out.get("checks", {}).get("hermes_authorship_ok") is False


def test_a3_rejects_orientg_gate_reply_source():
    """手测同路径：终稿出处 Orient-G门禁 必须硬挂。"""
    row = _row(PERSONNEL_COMPARE_QUERY, GOOD_PERSONNEL_COMPARE_EXCERPT, subject="A3-横比-深度")
    row["reply_source"] = "orientg_structured_gate"
    row["structured_gate_applied"] = True
    row["kb_supplemental"] = False
    row["hermes_kb_ask_calls"] = 2
    row["gateway_kb_ask_calls"] = 1
    row["hermes_mcp_retry_count"] = 0
    out = validate_row(row)
    assert out["ok"] is False
    assert out.get("checks", {}).get("hermes_authorship_ok") is False


def test_a3_rejects_dual_draft_process_glued_to_final():
    """手测同路径：主气泡过程稿+终稿粘贴（首轮取证…撰写终稿）必须硬挂。"""
    dual = (
        "首轮取证完成。证据显示可比公司A研发人员1,378人。需要第二轮不同query核证补缺。\n"
        "第二轮核证完成，证据一致。现在可以撰写终稿。"
        f"{GOOD_PERSONNEL_COMPARE_EXCERPT}"
    )
    row = _row(PERSONNEL_COMPARE_QUERY, dual, subject="A3-横比-深度")
    row["reply_source"] = "hermes"
    row["structured_gate_applied"] = False
    row["kb_supplemental"] = False
    row["hermes_kb_ask_calls"] = 2
    row["gateway_kb_ask_calls"] = 1
    row["hermes_mcp_retry_count"] = 0
    out = validate_row(row)
    assert out["ok"] is False
    assert (
        out.get("checks", {}).get("hand_path_dual_draft_ok") is False
        or out.get("checks", {}).get("no_process_in_answer") is False
        or "orchestration_dual_draft" in (out.get("checks", {}).get("forbidden_leaks") or [])
    )


def test_a3_rejects_process_draft_only_marked_hermes_complete():
    """假绿回归：仅英文 Let me first + 核证计划、无对照表，却标 Hermes 完成 → 必须硬挂。"""
    process_only = (
        "Let me first retrieve the personnel structure for both companies.\n\n"
        "evidence_sufficient=false。核证补缺计划：\n"
        "1. verification_queries: 可比公司A研发人员；YYCQ人员结构\n"
        "2. next_action=verify_gap_then_write_final\n"
        "Hermes 将继续调用 orientg_kb_ask。\n"
    )
    row = _row(PERSONNEL_COMPARE_QUERY, process_only, subject="A3-横比-深度")
    row["reply_source"] = "hermes"
    row["structured_gate_applied"] = False
    row["kb_supplemental"] = False
    row["hermes_kb_ask_calls"] = 4
    row["gateway_kb_ask_calls"] = 1
    row["hermes_mcp_retry_count"] = 0
    out = validate_row(row)
    assert out["ok"] is False
    checks = out.get("checks") or {}
    assert (
        checks.get("hermes_authorship_ok") is False
        or checks.get("personnel_core_table_ok") is False
        or checks.get("process_draft_final_ok") is False
        or checks.get("no_process_in_answer") is False
    )
    # 正文质量：禁止 Let me first；须有人员结构实质内容才可能绿
    assert re.search(r"Let me first", process_only, re.I)
    assert "人员结构对照" not in process_only


def test_a3_rejects_missing_retry_count_when_spec_requires_zero():
    """A3 缺 hermes_mcp_retry_count 不得默认当 0 刷绿。"""
    row = _row(PERSONNEL_COMPARE_QUERY, GOOD_PERSONNEL_COMPARE_EXCERPT, subject="A3-横比-深度")
    row["reply_source"] = "hermes"
    row["structured_gate_applied"] = False
    row["kb_supplemental"] = False
    row["hermes_kb_ask_calls"] = 2
    row["gateway_kb_ask_calls"] = 1
    # 显式缺省（validate 不得推断为 0）
    row.pop("hermes_mcp_retry_count", None)
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
        "分项合计\t—\t210人（excel 四项加总）\n"
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


def test_doc_folder_entity_scope_addon_maps_peera():
    """Tier0 synth 须被告知 PeerA25→可比公司A，避免「实体不明」拒答。"""
    from backend.services.agent_kb_supplemental import doc_folder_entity_scope_addon

    addon = doc_folder_entity_scope_addon({UD_37: "PeerA25", UD_YY: "25"})
    assert "可比公司A" in addon
    assert "YYCQ" in addon
    assert UD_37 in addon
    assert "禁止" in addon and "实体" in addon


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
    assert ("可比公司A" in out or "可比公司A" in out)
    assert ("YYCQ" in out or "YYCQ" in out)


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


D2_QUERY = "对比YYCQ与可比公司A2025年研发人员数量"
D1_QUERY = "对比YYCQ和可比公司A2025年销售与运营人员规模"
D2_MISATTR_BODY = (
    "结论：根据现有证据，无法提供可比公司A 2025年研发人员数量的具体数值，"
    "仅能提供YYCQ2025年研发人员数量为1,378人。\n"
    "主体\t2025年研发人员数量（人）\t2024年研发人员数量（人）\t变动比例\n"
    "YYCQ (YYCQ)\t1,378\t1,318\t4.55%\n"
    "可比公司A\t缺少证据\t缺少证据\t缺少证据\n"
    "说明：\n"
    "1. YYCQ数据：YYCQ2025年研发人员数量为1,378人。\n"
    "2. 可比公司A数据缺失。\n"
)
D1_INCOMPLETE_BODY = (
    "口径说明- YYCQ数据来自KB内excel「1.1信息-人员」。\n"
    "可比公司A研发数据来自年报，研发人员1,378人。\n"
    "由于KB作用域限制，可比公司A的销售/运营分项数据未能完整获取。\n"
)


def test_d2_browser_misattribution_detected_and_validate_fails():
    from backend.services.kb_ask_mcp_reply import personnel_compare_reply_misattributed

    assert personnel_compare_reply_misattributed(D2_MISATTR_BODY, user_query=D2_QUERY)
    row = validate_row(
        _row(D2_QUERY, D2_MISATTR_BODY, mode="fast", subject="D2-横比-研发", honest=True)
    )
    assert row["ok"] is False


@patch("backend.services.ai_interaction_llm._load_doc_chunk_text", side_effect=_chunk_loader)
def test_excerpts_assign_1378_to_peera_without_folder_labels(_mock_load):
    """正文无公司名、无 folder labels 时，仍须按切块内容把 1378→可比公司A、70→YYCQ。"""
    from backend.services.kb_ask_mcp_reply import build_personnel_compare_excerpts

    excerpts = build_personnel_compare_excerpts(
        [{"doc_id": UD_37, "chunk_id": "c1"}, {"doc_id": UD_YY, "chunk_id": "c2"}],
        D2_QUERY,
        tenant_id="tenant1",
        fixtures={},
        doc_folder_labels=None,
    )
    by_ent = {str(e.get("entity")): e for e in excerpts}
    assert "可比公司A" in by_ent
    assert "YYCQ" in by_ent
    assert re.search(r"1[,，]?378|1378", by_ent["可比公司A"]["excerpt"])
    assert re.search(r"70", by_ent["YYCQ"]["excerpt"])
    assert not re.search(r"1[,，]?378|1378", by_ent["YYCQ"]["excerpt"])


@patch("backend.services.ai_interaction_llm._load_doc_chunk_text", side_effect=_chunk_loader)
def test_fast_path_d2_rejects_1378_on_yycq(_mock_load):
    from backend.services.agent_kb_fast_path import _apply_personnel_fast_path_reply
    from backend.services.kb_ask_mcp_reply import personnel_compare_reply_misattributed

    prefetch = {
        "ok": True,
        "citations": [
            {"doc_id": UD_37, "chunk_id": "c1"},
            {"doc_id": UD_YY, "chunk_id": "c2"},
        ],
        "evidence_pack": {"task_type": "compare"},
    }
    out = _apply_personnel_fast_path_reply(
        synth_reply=D2_MISATTR_BODY,
        user_query=D2_QUERY,
        prefetch_result=prefetch,
        tenant_id="tenant1",
        fixtures={"tenant_id": "tenant1"},
        kb_scope=None,
    )
    assert not personnel_compare_reply_misattributed(out, user_query=D2_QUERY)
    assert re.search(r"1[,，]?378|1378", out)
    assert re.search(r"(?<!\d)70(?!\d)", out)
    row = validate_row(_row(D2_QUERY, out, mode="fast", subject="D2-横比-研发"))
    assert row["ok"] is True


@patch("backend.services.ai_interaction_llm._load_doc_chunk_text", side_effect=_chunk_loader)
def test_native_structured_gate_fixes_d2_misattribution(_mock_load, monkeypatch):
    """native：不得因「结论/口径」短分析放行 1378→YYCQ 错稿。"""
    from backend.config import settings
    from backend.services.agent_kb_supplemental import apply_personnel_structured_final_gate
    from backend.services.kb_ask_mcp_reply import personnel_compare_reply_misattributed

    monkeypatch.setattr(settings, "hermes_native_mcp_reply", True)
    monkeypatch.setattr(settings, "hermes_native_skip_supplemental", True)
    prefetch = {
        "ok": True,
        "citations": [
            {"doc_id": UD_37, "chunk_id": "c1"},
            {"doc_id": UD_YY, "chunk_id": "c2"},
        ],
        "evidence_pack": {"task_type": "compare"},
    }
    out, _applied = apply_personnel_structured_final_gate(
        D2_MISATTR_BODY,
        prefetch_result=prefetch,
        user_query=D2_QUERY,
        tenant_id="tenant1",
        fixtures={"tenant_id": "tenant1"},
    )
    assert not personnel_compare_reply_misattributed(out, user_query=D2_QUERY)
    assert re.search(r"1[,，]?378|1378", out)
    assert re.search(r"(?<!\d)70(?!\d)", out)


@patch("backend.services.ai_interaction_llm._load_doc_chunk_text", side_effect=_chunk_loader)
def test_native_structured_gate_fixes_d1_missing_sanqi_roles(_mock_load, monkeypatch):
    """D1 问销售/运营：native 下不得放行仅有 1378、缺 946/242 的短口径稿。"""
    from backend.config import settings
    from backend.services.agent_kb_supplemental import apply_personnel_structured_final_gate

    monkeypatch.setattr(settings, "hermes_native_mcp_reply", True)
    monkeypatch.setattr(settings, "hermes_native_skip_supplemental", True)
    prefetch = {
        "ok": True,
        "citations": [
            {"doc_id": UD_37, "chunk_id": "c1"},
            {"doc_id": UD_YY, "chunk_id": "c2"},
        ],
        "evidence_pack": {"task_type": "compare"},
    }
    out, _applied = apply_personnel_structured_final_gate(
        D1_INCOMPLETE_BODY,
        prefetch_result=prefetch,
        user_query=D1_QUERY,
        tenant_id="tenant1",
        fixtures={"tenant_id": "tenant1"},
    )
    assert re.search(r"946", out) and re.search(r"242", out)
    row = validate_row(_row(D1_QUERY, out, mode="standard", subject="D1-横比-职能"))
    assert row["ok"] is True


D1_SWAP_BODY = (
    "YYCQ2025年人员数据：总员工：3,138人；销售人员：946人；运营人员：242人\n"
    "可比公司A2025年人员数据：总员工：139人；销售人员：10人；研发人员：95人\n"
    "##人员结构对照\n|职能归属 |可比公司A | YYCQ |\n"
    "|销售人员 |10 |946 |\n|运营人员 |证据未覆盖 |242 |\n"
    "人员规模差异显著：YYCQ总员工3,138人，可比公司A仅139人，前者约22.6倍。"
)


def test_d1_entity_swap_misattribution_detected():
    from backend.services.kb_ask_mcp_reply import personnel_compare_reply_misattributed

    assert personnel_compare_reply_misattributed(D1_SWAP_BODY, user_query=D1_QUERY)
    row = validate_row(_row(D1_QUERY, D1_SWAP_BODY, mode="standard", subject="D1-横比-职能"))
    assert row["ok"] is False


@patch("backend.services.ai_interaction_llm._load_doc_chunk_text", side_effect=_chunk_loader)
def test_native_structured_gate_fixes_d1_entity_swap(_mock_load, monkeypatch):
    """D1：Hermes 把 PeerA 3138/946 挂 YYCQ、139 挂可比公司A 时须纠偏。"""
    from backend.config import settings
    from backend.services.agent_kb_supplemental import apply_personnel_structured_final_gate
    from backend.services.kb_ask_mcp_reply import personnel_compare_reply_misattributed

    monkeypatch.setattr(settings, "hermes_native_mcp_reply", True)
    monkeypatch.setattr(settings, "hermes_native_skip_supplemental", True)
    prefetch = {
        "ok": True,
        "citations": [
            {"doc_id": UD_37, "chunk_id": "c1"},
            {"doc_id": UD_YY, "chunk_id": "c2"},
        ],
        "evidence_pack": {"task_type": "compare"},
    }
    out, applied = apply_personnel_structured_final_gate(
        D1_SWAP_BODY,
        prefetch_result=prefetch,
        user_query=D1_QUERY,
        tenant_id="tenant1",
        fixtures={"tenant_id": "tenant1"},
    )
    assert applied is True
    assert not personnel_compare_reply_misattributed(out, user_query=D1_QUERY)
    assert re.search(r"946", out) and re.search(r"242", out)
    assert "22.6" not in out
    row = validate_row(_row(D1_QUERY, out, mode="standard", subject="D1-横比-职能"))
    assert row["ok"] is True


def test_a3_rejects_stacked_names_and_excel_sum_as_headcount():
    """手测/CDP：叠名表头、把分项加总当员工总数并推 22 倍 → 拒收。"""
    bad = (
        "### 人员结构对照\n"
        "职能归属\t可比公司A\tYYCQ\n"
        "研发人员\t1,378人\t70人\n"
        "销售人员\t946人\t证据未覆盖\n"
        "运营人员\t242人\t61人\n"
        "员工总数\t3,138人\t140 人\n"
        "对比分析\n"
        "可比公司A3,138人，YYCQ140人，前者约为后者的22倍量级。\n"
        "分项合计\t—\t210人\n"
    )
    row = _row(PERSONNEL_COMPARE_QUERY, bad, subject="A3-横比-深度")
    row["reply_source"] = "hermes"
    row["structured_gate_applied"] = False
    row["kb_supplemental"] = False
    row["hermes_kb_ask_calls"] = 2
    row["gateway_kb_ask_calls"] = 1
    row["hermes_mcp_retry_count"] = 0
    out = validate_row(row)
    assert out["ok"] is False
    leaks = out.get("checks", {}).get("forbidden_leaks") or []
    assert leaks, out.get("checks")


def test_b1_conflict_note_139_vs_3138_is_not_excel_sum_leak():
    """B1：主答用年报 3,138，并诚实注明冲突片段中的 139/95 → 不得误杀 excel_sum_as_headcount。"""
    from finance_matrix_personnel_validate import personnel_compare_has_forbidden_leaks

    good = (
        "可比公司A2025年末在职员工数量为3,138人。\n"
        "按专业构成：销售人员946人、研发人员1,066人、运营/其他职能部门人员561人、"
        "管理人员312人、财务人员102人、行政人员115人、其他人员36人。\n"
        "教育程度：本科2,178人、硕士及以上321人、大专及以下639人。\n"
        "指标\t2025年年末数量（人）\n"
        "在职员工数量合计\t3,138\n"
        "销售人员\t946\n"
        "说明：\n"
        "1. 来自证据中的「期末在职员工数量合计」及专业构成明细。\n"
        "2. 运营/其他职能部门人员合计为242+319=561人。\n"
        "3. 其他证据片段披露的员工总数（139人或95人）与披露的3,138人存在显著差异，"
        "且未提供明确的合并口径说明；本答以年报主体口径3,138为准。\n"
    )
    leaks = personnel_compare_has_forbidden_leaks(good)
    assert "excel_sum_as_headcount" not in leaks, leaks
    row = _row(
        "可比公司A2025年员工数量、专业构成及教育程度",
        good,
        mode="fast",
        subject="B1-可比公司A-员工专节",
    )
    out = validate_row(row)
    assert out["ok"] is True, out.get("checks")
