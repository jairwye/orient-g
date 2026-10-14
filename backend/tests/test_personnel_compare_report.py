"""人员结构横比成稿与通用验收（TDD）。"""

from __future__ import annotations

import re

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
CN_QUERY = QUERY
CANON_QUERY = "对比分析YYCQ和可比公司A25年的人员结构"


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


def test_misattribution_huaqing_139_on_yycq_chinese_names():
    """浏览器实问「YYCQ/可比公司A」时，139 挂本公司侧仍须判误归因（不依赖 YYCQ 字面）。"""
    from backend.services.kb_ask_mcp_reply import personnel_compare_reply_misattributed

    q = "对比分析YYCQ和可比公司A25年的人员结构"
    bad = (
        "结论：YYCQ为小型游戏公司，员工仅139人。\n"
        "### 核心指标对比\n"
        "|指标|可比公司A|YYCQ|\n"
        "|员工总数|3,138人|139人|\n"
        "|研发人员数量|1,378人|70人（间接数据）/95人|\n"
        "YYCQ 1.1信息-人员 研发70。\n"
    )
    assert personnel_compare_reply_misattributed(bad, user_query=q)

    good = (
        "### 人员结构对照\n"
        "| 职能归属 | 可比公司A | YYCQ |\n"
        "| 研发 | 1378 人 | 70 人 |\n"
        "| 销售 | 946 人 | 证据未覆盖 |\n"
        "| 运营 | 242 人 | 61 人 |\n"
        "### 对比分析\n结构差异；两侧口径不同，不可直接比员工总数。\n"
    )
    assert not personnel_compare_reply_misattributed(good, user_query=q)


def test_misattribution_约139_on_youyi_with_excel70():
    """过程稿把华清 139 与 excel 70 并列挂YYCQ → 误归因。"""
    from backend.services.kb_ask_mcp_reply import personnel_compare_reply_misattributed

    q = "对比分析YYCQ和可比公司A25年的人员结构"
    bad = (
        "YYCQ：运营61、研发70、支持45.85，分项合计210。\n"
        "来源2：期末员工总计139人。技术人员95人。\n"
        "可比公司A：员工3,138；研发1,378；销售946；运营242。\n"
        "### 人员结构对照\n"
        "职能归属\t可比公司A\tYYCQ\n"
        "研发人员\t1,066\t95\n"
        "结论：YYCQ约139-210人。\n"
    )
    assert personnel_compare_reply_misattributed(bad, user_query=q)


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


DISPLAY_QUERY = "对比分析甲公司和乙公司25年的人员结构"
_PRIMARY_DISPLAY = "甲公司"
_PEER_DISPLAY = "乙公司"


def _patch_display_aliases(monkeypatch):
    from backend.config import settings
    from backend.services import kb_compare_entities as ce

    monkeypatch.setattr(settings, "kb_compare_entity_primary_aliases", _PRIMARY_DISPLAY)
    monkeypatch.setattr(settings, "kb_compare_entity_peer_aliases", _PEER_DISPLAY)
    monkeypatch.setattr(
        settings,
        "kb_compare_entity_extra_markers",
        f"{_PRIMARY_DISPLAY},{_PEER_DISPLAY}",
    )
    monkeypatch.setenv("KB_COMPARE_ENTITY_PRIMARY_ALIASES", _PRIMARY_DISPLAY)
    monkeypatch.setenv("KB_COMPARE_ENTITY_PEER_ALIASES", _PEER_DISPLAY)
    monkeypatch.setenv(
        "KB_COMPARE_ENTITY_EXTRA_MARKERS", f"{_PRIMARY_DISPLAY},{_PEER_DISPLAY}"
    )
    ce.clear_compare_entity_cache()
    return ce


def test_present_entity_label_prefers_user_query_names(monkeypatch):
    ce = _patch_display_aliases(monkeypatch)
    try:
        assert ce.present_entity_label("YYCQ", DISPLAY_QUERY) == _PRIMARY_DISPLAY
        assert ce.present_entity_label("可比公司A", DISPLAY_QUERY) == _PEER_DISPLAY
        assert ce.present_entity_label("YYCQ", CANON_QUERY) == "YYCQ"
    finally:
        ce.clear_compare_entity_cache()


def test_structured_report_uses_user_facing_names_not_canonical(monkeypatch):
    ce = _patch_display_aliases(monkeypatch)
    try:
        sanqi = (
            "公司研发人员情况\n研发人员数量（人） | 1,378 | 1,318\n研发人员数量占比 43.91%\n\n"
            "1、员工数量、专业构成及教育程度\n"
            "| 在职员工的数量合计（人） | 3,138 |\n"
            "| 销售人员 | 946 |\n| 运营人员 其他职能部门人员 | 242 319 |\n"
            "| 行政人员 | 36 |\n| 技术人员 | 312 |"
        )
        yycq = (
            "1.1信息-人员\n| 运营 | 61.00 |\n| 管理 | 33.15 |\n| 研发 | 70.00 |\n| 支持 | 45.85 |"
        )
        out = format_personnel_compare_structured_report(
            [{"entity": "可比公司A", "excerpt": sanqi}, {"entity": "YYCQ", "excerpt": yycq}],
            user_query=DISPLAY_QUERY,
        )
        assert out
        assert _PRIMARY_DISPLAY in out and _PEER_DISPLAY in out
        assert not re.search(r"\|\s*职能归属\s*\|\s*可比公司A\s*\|\s*YYCQ\s*\|", out)
        assert "分项合计" in out
        assert "33.15" in out and "45.85" in out
        assert re.search(r"3[,，]?138", out)
        assert "| **员工总数（年报）** |" in out or "员工总数" in out
    finally:
        ce.clear_compare_entity_cache()


def test_rewrite_reply_present_entity_labels(monkeypatch):
    ce = _patch_display_aliases(monkeypatch)
    try:
        raw = (
            "### 人员结构对照\n"
            "| 职能归属 | 可比公司A | YYCQ |\n"
            "| 研发 | 1378 人 | 70 人 |\n"
        )
        out = ce.rewrite_reply_present_entity_labels(raw, DISPLAY_QUERY)
        assert _PEER_DISPLAY in out and _PRIMARY_DISPLAY in out
        assert "可比公司A" not in out
        assert not re.search(r"\bYYCQ\b", out)
    finally:
        ce.clear_compare_entity_cache()


def test_validate_rejects_canonical_table_headers_for_chinese_query(monkeypatch):
    from backend.scripts.finance_matrix_personnel_validate import personnel_compare_answer_ok

    ce = _patch_display_aliases(monkeypatch)
    try:
        bad = (
            "## YYCQ vs 可比公司A · 2025 人员结构对比\n\n"
            "### 人员结构对照\n\n"
            "| 职能归属 | 可比公司A | YYCQ |\n"
            "| --- | --- | --- |\n"
            "| 研发 | 1378 人（占员工 43.91%） | 70 人 |\n"
            "| 运营 | 242 人 | 61 人 |\n"
            "| 管理 | 36 人 | 33.15 人 |\n"
            "| 支持 | 312 人 | 45.85 人 |\n"
            "| 销售 | 946 人 | 证据未覆盖 |\n"
            "| **分项合计** | — | **210 人**（excel 四项加总） |\n\n"
            "### 对比分析\n\n"
            "- **结构差异**：YYCQ为 excel 职能四分项。\n"
        )
        ok, checks = personnel_compare_answer_ok(
            bad,
            user_query=DISPLAY_QUERY,
            mode="deep",
            hermes_kb_ask_calls=2,
        )
        assert ok is False
        assert checks.get("canonical_headers_leaked") is True

        good = (
            f"## {_PRIMARY_DISPLAY} vs {_PEER_DISPLAY} · 2025 人员结构对比\n\n"
            "### 人员结构对照\n\n"
            f"| 职能归属 | {_PEER_DISPLAY} | {_PRIMARY_DISPLAY} |\n"
            "| --- | --- | --- |\n"
            "| 研发 | 1378 人（占员工 43.91%） | 70 人 |\n"
            "| 运营 | 242 人 | 61 人 |\n"
            "| 管理 | 36 人 | 33.15 人 |\n"
            "| 支持 | 312 人 | 45.85 人 |\n"
            "| 销售 | 946 人 | 证据未覆盖 |\n"
            "| **分项合计** | — | **210 人**（excel 四项加总） |\n"
            "| **员工总数（年报）** | **3138 人** | — |\n\n"
            "### 对比分析\n\n"
            f"- **结构差异**：{_PRIMARY_DISPLAY}为 excel 职能四分项；"
            f"{_PEER_DISPLAY}为年报专业构成。\n"
        )
        ok2, checks2 = personnel_compare_answer_ok(
            good,
            user_query=DISPLAY_QUERY,
            mode="deep",
            hermes_kb_ask_calls=2,
        )
        assert ok2 is True, checks2
        assert checks2.get("canonical_headers_leaked") is not True
    finally:
        ce.clear_compare_entity_cache()


def test_rewrite_reply_collapses_stacked_present_labels(monkeypatch):
    """展示名经 rewrite 不得叠成「乙公司（乙公司）」。"""
    ce = _patch_display_aliases(monkeypatch)
    try:
        raw = (
            "### 人员结构对照\n"
            f"| 职能归属 | 可比公司A（{_PEER_DISPLAY}） | YYCQ（{_PRIMARY_DISPLAY}） |\n"
            "| 研发 | 1378 | 70 |\n"
            f"可比公司A（即用户所称{_PEER_DISPLAY}）侧为年报口径。\n"
        )
        out = ce.rewrite_reply_present_entity_labels(raw, DISPLAY_QUERY)
        assert f"{_PEER_DISPLAY}（{_PEER_DISPLAY}）" not in out
        assert f"{_PRIMARY_DISPLAY}（{_PRIMARY_DISPLAY}）" not in out
        assert _PEER_DISPLAY in out and _PRIMARY_DISPLAY in out
        assert not re.search(r"\bYYCQ\b", out)
    finally:
        ce.clear_compare_entity_cache()
