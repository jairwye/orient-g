"""人员结构浏览器实测 · 新矩阵 case spec 验收（1.2.3.c）。"""

from __future__ import annotations

from backend.scripts.finance_matrix_personnel_cases import (
    PERSONNEL_CASE_SPECS,
    PERSONNEL_MATRIX,
    personnel_case_spec,
)
from backend.scripts.finance_matrix_personnel_validate import (
    GOOD_PERSONNEL_COMPARE_EXCERPT,
    validate_personnel_case_spec,
)
from backend.scripts.finance_matrix_browser_validate import validate_row


def test_personnel_matrix_has_eight_cases_with_specs():
    assert len(PERSONNEL_MATRIX) == 8
    subjects = [c[1] for c in PERSONNEL_MATRIX]
    assert subjects == list(PERSONNEL_CASE_SPECS.keys())


def test_a3_spec_rejects_incomplete_sanqi_table():
    bad = (
        "## YYCQ vs 可比公司A · 2025 人员结构对比\n\n"
        "### 人员结构对照\n\n"
        "| 职能归属 | 可比公司A | YYCQ |\n"
        "| --- | --- | --- |\n"
        "| 研发 | 1378 人 | 70 人 |\n"
        "| 运营 | 证据未覆盖 | 61 人 |\n"
        "| 销售 | 证据未覆盖 | 证据未覆盖 |\n\n"
        "### 对比分析\n\n- **结构差异**\n"
    )
    spec = personnel_case_spec("A3-横比-深度")
    assert spec
    ok, checks = validate_personnel_case_spec(
        bad,
        spec=spec,
        mode="deep",
        hermes_kb_ask_calls=3,
        hermes_only_kb_ask_calls=2,
        gateway_kb_ask_calls=1,
        hermes_mcp_retry_count=0,
        reply_source="hermes",
        structured_gate_applied=False,
        kb_supplemental=False,
        user_query="对比分析YYCQ和可比公司A25年的人员结构",
    )
    assert ok is False
    assert checks.get("sanqi_roles_in_table_ok") is False


def test_a1_spec_accepts_good_excerpt():
    spec = personnel_case_spec("A1-横比-快速")
    assert spec
    ok, checks = validate_personnel_case_spec(
        GOOD_PERSONNEL_COMPARE_EXCERPT,
        spec=spec,
        mode="fast",
        user_query="对比分析YYCQ和可比公司A25年的人员结构",
    )
    assert ok is True
    assert checks.get("has_946")
    assert checks.get("has_242")


def test_b1_spec_requires_sanqi_staff_anchors():
    spec = personnel_case_spec("B1-可比公司A-员工专节")
    assert spec
    ok, _ = validate_personnel_case_spec(
        "销售人员 946 人；运营人员 242 人；在职员工合计 3138 人。",
        spec=spec,
        mode="fast",
    )
    assert ok is True
    ok2, _ = validate_personnel_case_spec(
        "研发人员 1378 人，占比 43.91%。",
        spec=spec,
        mode="fast",
    )
    assert ok2 is False


def test_validate_row_uses_case_spec_for_a2():
    row = validate_row(
        {
            "category": "personnel",
            "subject": "A2-横比-标准",
            "mode": "standard",
            "query": "对比分析YYCQ和可比公司A25年的人员结构",
            "tier_line": "●完成：Tier 1（Hermes 标准编排）",
            "citations": 12,
            "streamDone": True,
            "orientg_kb_ask_calls": 3,
            "extract": {
                "hasMoney": False,
                "honestMissing": False,
                "head": GOOD_PERSONNEL_COMPARE_EXCERPT,
                "len": len(GOOD_PERSONNEL_COMPARE_EXCERPT),
                "streamFail": False,
            },
        }
    )
    assert row["checks"].get("personnel_subject") == "A2-横比-标准"
    assert row["ok"] is True


def test_incomplete_table_fails_stream_personnel_structured_check():
    from backend.scripts.finance_matrix_browser_validate import _personnel_structured_final_ok

    bad = (
        GOOD_PERSONNEL_COMPARE_EXCERPT.replace("| 运营 | 242 人 |", "| 运营 | 证据未覆盖 |")
        .replace("| 销售 | 946 人 |", "| 销售 | 证据未覆盖 |")
    )
    row = {
        "mode": "deep",
        "query": "对比分析YYCQ和可比公司A25年的人员结构",
        "extract": {"len": len(bad)},
    }
    assert _personnel_structured_final_ok(row, bad) is False
