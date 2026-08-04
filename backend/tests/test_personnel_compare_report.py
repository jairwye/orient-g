"""人员结构横比成稿与通用验收（TDD）。"""

from __future__ import annotations

from backend.services.personnel_compare_report import (
    format_personnel_compare_structured_report,
    personnel_excerpt_dump_only,
    personnel_reply_has_analysis,
)
from backend.scripts.finance_matrix_personnel_validate import (
    BROWSER_FAIL_HERMES_V1,
    GOOD_PERSONNEL_COMPARE_EXCERPT,
    personnel_compare_answer_ok,
)

QUERY = "对比分析YYCQ和可比公司A25年的人员结构"


def test_structured_report_has_analysis_not_dump():
    excerpts = [
        {
            "entity": "可比公司A",
            "excerpt": "公司研发人员情况\n研发人员数量（人） | 1,378 | 1,318\n研发人员数量占比 43.91%",
        },
        {
            "entity": "YYCQ",
            "excerpt": "1.1信息-人员\n研发 | 70.00\n运营 | 61.00",
        },
    ]
    out = format_personnel_compare_structured_report(excerpts, user_query=QUERY)
    assert out
    assert "### 人员结构对照" in out
    assert "### 对比分析" in out
    assert not personnel_excerpt_dump_only(out)
    assert personnel_reply_has_analysis(out)


def test_generic_validate_rejects_misattribution():
    ok, checks = personnel_compare_answer_ok(BROWSER_FAIL_HERMES_V1, user_query=QUERY)
    assert ok is False
    assert checks.get("misattributed")


def test_generic_validate_accepts_structured_excerpt():
    ok, checks = personnel_compare_answer_ok(
        GOOD_PERSONNEL_COMPARE_EXCERPT,
        user_query=QUERY,
        mode="deep",
        hermes_kb_ask_calls=4,
    )
    assert ok is True
    assert checks.get("personnel_compare_ok")
    assert checks.get("personnel_core_table_ok")
    assert checks.get("deep_mcp_required") is not False


def test_generic_validate_deep_requires_mcp_and_core_table():
    ok, checks = personnel_compare_answer_ok(
        GOOD_PERSONNEL_COMPARE_EXCERPT,
        user_query=QUERY,
        mode="deep",
        hermes_kb_ask_calls=None,
    )
    assert ok is False
    assert checks.get("deep_mcp_required") is False

    hermes_only = (
        "基于证据对YYCQ与可比公司A2025年人员结构对比分析如下。\n"
        "可比公司A：研发人员1378人，占比43.91%。\n"
        "YYCQ：excel分项研发70人。\n"
        "对比分析：两家口径不同，结构差异见各主体 section。\n"
    )
    ok2, checks2 = personnel_compare_answer_ok(
        hermes_only,
        user_query=QUERY,
        mode="deep",
        hermes_kb_ask_calls=2,
    )
    assert ok2 is False
    assert checks2.get("personnel_core_table_ok") is False


def test_misattribution_huaqing_139_on_yycq():
    from backend.services.kb_ask_mcp_reply import personnel_compare_reply_misattributed

    bad = (
        "YYCQ 1.1信息-人员 研发70人。\n"
        "YYCQ 研发人员情况 期末95人 占68.3%。\n"
        "在职员工 期末139人。\n"
    )
    assert personnel_compare_reply_misattributed(bad, user_query=QUERY)


def test_excel_rd_rejects_truncated_chunk_false_one():
    from backend.services.personnel_compare_report import _extract_entity_metrics

    truncated = "1.1信息-人员\n| 研发 | | 1.00 |"
    assert _extract_entity_metrics(truncated, entity="YYCQ").get("rd_count") is None

    full = (
        "1.1信息-人员\n| 1.10 | 人员情况 | YYCQ | 2025全年 | 2025-12-31 | 研发 | | 70.00 | |"
    )
    assert _extract_entity_metrics(full, entity="YYCQ").get("rd_count") == "70"


def test_validate_rejects_yycq_rd_one_in_core_table():
    bad = GOOD_PERSONNEL_COMPARE_EXCERPT.replace("| 70 人 |", "| 1 人 |", 1)
    ok, checks = personnel_compare_answer_ok(
        bad,
        user_query=QUERY,
        mode="deep",
        hermes_kb_ask_calls=2,
    )
    assert ok is False
    assert checks.get("yycq_rd_parse_ok") is False


def test_structured_report_yycq_rd_in_table():
    import re

    excerpts = [
        {
            "entity": "可比公司A",
            "excerpt": "公司研发人员情况\n研发人员数量（人） | 1,378 | 1,318\n研发人员数量占比 43.91%",
        },
        {
            "entity": "YYCQ",
            "excerpt": (
                "1.1信息-人员\n| 编码 | 分类 | 一级人员归属 | 人数 |\n"
                "| 1.10 | 人员情况 | 研发 | | 70.00 |"
            ),
        },
    ]
    out = format_personnel_compare_structured_report(excerpts, user_query=QUERY)
    assert out
    assert re.search(r"\|\s*研发\s*\|[^|\n]*\|\s*70", out)


def test_personnel_compare_needs_gate_when_sanqi_table_incomplete():
    from backend.services.personnel_compare_report import (
        personnel_compare_needs_structured_gate,
        personnel_compare_sanqi_table_incomplete,
    )
    from backend.scripts.finance_matrix_personnel_validate import GOOD_PERSONNEL_COMPARE_EXCERPT

    bad = GOOD_PERSONNEL_COMPARE_EXCERPT.replace(
        "| 销售 | 946 人 |",
        "| 销售 | 证据未覆盖（节选无该分项） |",
    )
    assert personnel_compare_sanqi_table_incomplete(bad)
    assert personnel_compare_needs_structured_gate(bad, user_query=QUERY)


def test_structured_report_sanqi_staff_professional_breakdown():
    sanqi = (
        "公司研发人员情况\n研发人员数量（人） | 1,378 | 1,318\n研发人员数量占比 43.91%\n\n"
        "1、员工数量、专业构成及教育程度\n"
        "| 销售人员 | 946 |\n| 运营人员 其他职能部门人员 | 242 319 |\n"
        "| 行政人员 | 36 |\n| 技术人员 | 312 |"
    )
    yycq = (
        "1.1信息-人员\n| 运营 | 61.00 |\n| 管理 | 33.15 |\n| 研发 | 70.00 |\n| 支持 | 45.85 |"
    )
    out = format_personnel_compare_structured_report(
        [{"entity": "可比公司A", "excerpt": sanqi}, {"entity": "YYCQ", "excerpt": yycq}],
        user_query=QUERY,
    )
    assert out
    assert "| 销售 | 946 人 |" in out
    assert "| 运营 | 242 人 |" in out
    assert "1378" in out
    assert "证据未覆盖（节选无该分项）" not in out.split("| 销售 |")[1].split("\n")[0]


def test_generic_validate_rejects_old_excerpt_dump():
    old_dump = (
        "## YYCQ vs 可比公司A · 2025 人员结构对比\n"
        "以下对比基于知识库 docling section / excel chunk 证据（非硬编码数值）。\n"
        "### 可比公司A\n\n| 研发 | 1378 |\n\n### YYCQ\n\n| 研发 | 70 |\n\n"
        "## 对比说明\n口径可能不同。"
    )
    ok, _ = personnel_compare_answer_ok(
        old_dump,
        user_query=QUERY,
        mode="deep",
        hermes_kb_ask_calls=2,
    )
    assert ok is False


def test_personnel_compare_needs_structured_gate():
    from backend.services.personnel_compare_report import personnel_compare_needs_structured_gate

    hermes = (
        "## YYCQ vs 可比公司A · 2025 人员结构对比\n"
        "可比公司A 研发 1378 | YYCQ 研发 70\n"
        "对比分析：两家口径不同。\n"
    )
    assert personnel_compare_needs_structured_gate(hermes, user_query=QUERY)
    assert not personnel_compare_needs_structured_gate(
        GOOD_PERSONNEL_COMPARE_EXCERPT,
        user_query=QUERY,
    )
