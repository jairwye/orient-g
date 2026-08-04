"""人员结构浏览器实测矩阵（竞品财报25 · finance_test）。

规制：specs/plans/1.2.3.c-personnel-browser-testing.md
与 42 条财务矩阵独立报告：finance_matrix_personnel_browser_report.json
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, TypedDict

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from finance_matrix_cases import MODE_LABEL, TIER_EXPECT  # noqa: E402

PERSONNEL_COMPARE_QUERY = "对比分析YYCQ和可比公司A25年的人员结构"


class PersonnelCaseSpec(TypedDict, total=False):
    """单条用例验收期望（供 validate / retry_queue / Agent 提示）。"""

    group: str
    angle: str
    tier_expect: str
    must_contain: list[str]
    must_not_contain: list[str]
    require_sanqi_roles: bool
    require_core_table: bool
    require_analysis: bool
    kb_section_hint: str
    require_hermes_authorship: bool
    max_gateway_kb_ask_calls: int
    min_hermes_kb_ask_calls: int
    max_hermes_mcp_retry_count: int


# (category, subject, mode, query)
PERSONNEL_MATRIX: list[tuple[str, str, str, str]] = [
    # A · 横比结构化终稿（三档同问句，终稿标准一致）
    (
        "personnel",
        "A1-横比-快速",
        "fast",
        PERSONNEL_COMPARE_QUERY,
    ),
    (
        "personnel",
        "A2-横比-标准",
        "standard",
        PERSONNEL_COMPARE_QUERY,
    ),
    (
        "personnel",
        "A3-横比-深度",
        "deep",
        PERSONNEL_COMPARE_QUERY,
    ),
    # B · KB 切块可达性（gate 数据源）
    (
        "personnel",
        "B1-可比公司A-员工专节",
        "fast",
        "可比公司A2025年员工数量、专业构成及教育程度",
    ),
    (
        "personnel",
        "B2-可比公司A-研发专节",
        "fast",
        "可比公司A2025年研发人员情况",
    ),
    (
        "personnel",
        "C1-YYCQ-excel分项",
        "fast",
        "YYCQ2025年1.1信息-人员",
    ),
    # D · 问法变体
    (
        "personnel",
        "D1-横比-职能",
        "standard",
        "对比YYCQ和可比公司A2025年销售与运营人员规模",
    ),
    (
        "personnel",
        "D2-横比-研发",
        "fast",
        "对比YYCQ与可比公司A2025年研发人员数量",
    ),
]

PERSONNEL_CASE_SPECS: dict[str, PersonnelCaseSpec] = {
    "A1-横比-快速": {
        "group": "A",
        "angle": "Tier0 本地结构化终稿；不依赖 Hermes 成稿",
        "tier_expect": "Tier 0",
        "must_contain": ["人员结构对照", "946", "242", "1378", "70"],
        "must_not_contain": ["139人的22.6倍", "Let me search", "分主体证据摘要"],
        "require_sanqi_roles": True,
        "require_core_table": True,
        "require_analysis": True,
    },
    "A2-横比-标准": {
        "group": "A",
        "angle": "Tier1 Hermes lite + Orient-G structured gate",
        "tier_expect": "Tier 1",
        "must_contain": ["人员结构对照", "946", "242", "1378", "70"],
        "must_not_contain": ["139人的22.6倍", "Let me search", "分主体证据摘要"],
        "require_sanqi_roles": True,
        "require_core_table": True,
        "require_analysis": True,
    },
    "A3-横比-深度": {
        "group": "A",
        "angle": (
            "Tier2 Hermes 深度主写；禁 gate 模板；gateway≤2；"
            "多轮 MCP（取证+核证 hermes≥2）；首轮即 MCP（retry=0）；"
            "禁推算/推断；择优保住对照表；禁「成稿骨架」终稿"
        ),
        "tier_expect": "Tier 2",
        "must_contain": ["人员结构对照", "946", "242", "1378", "70"],
        "must_not_contain": [
            "139人的22.6倍",
            "Let me search",
            "分主体证据摘要",
            "推算",
            "请勿采信",
            "成稿骨架",
            "请原样采用下列数字",
        ],
        "require_sanqi_roles": True,
        "require_core_table": True,
        "require_analysis": True,
        "require_hermes_authorship": True,
        "max_gateway_kb_ask_calls": 2,
        "min_hermes_kb_ask_calls": 2,
        "max_hermes_mcp_retry_count": 0,
    },
    "B1-可比公司A-员工专节": {
        "group": "B",
        "angle": "年报「员工数量、专业构成及教育程度」chunk 可达",
        "tier_expect": "Tier 0",
        "must_contain": ["946", "242"],
        "must_not_contain": [],
        "require_sanqi_roles": False,
        "require_core_table": False,
        "kb_section_hint": "员工数量、专业构成及教育程度",
    },
    "B2-可比公司A-研发专节": {
        "group": "B",
        "angle": "年报「研发人员情况」chunk 可达",
        "tier_expect": "Tier 0",
        "must_contain": ["1378"],
        "must_not_contain": [],
        "require_sanqi_roles": False,
        "require_core_table": False,
        "kb_section_hint": "研发人员情况",
    },
    "C1-YYCQ-excel分项": {
        "group": "C",
        "angle": "excel 1.1信息-人员 分项可达",
        "tier_expect": "Tier 0",
        "must_contain": ["70"],
        "must_not_contain": [],
        "require_sanqi_roles": False,
        "require_core_table": False,
        "kb_section_hint": "1.1信息-人员",
    },
    "D1-横比-职能": {
        "group": "D",
        "angle": "职能口径问法仍须拉出可比公司A销售/运营",
        "tier_expect": "Tier 1",
        "must_contain": ["946", "242"],
        "must_not_contain": ["139人的22.6倍"],
        "require_sanqi_roles": True,
        "require_core_table": False,
        "require_analysis": False,
    },
    "D2-横比-研发": {
        "group": "D",
        "angle": "窄口径研发横比；禁止错归属 1378→YYCQ",
        "tier_expect": "Tier 0",
        "must_contain": ["1378", "70"],
        "must_not_contain": ["139人的22.6倍", "1,378人显然不可能"],
        "require_sanqi_roles": False,
        "require_core_table": False,
    },
}


def personnel_case_spec(subject: str) -> PersonnelCaseSpec | None:
    return PERSONNEL_CASE_SPECS.get(subject)


def personnel_case_spec_for_row(row: dict[str, Any]) -> PersonnelCaseSpec | None:
    return personnel_case_spec(str(row.get("subject") or ""))


SUITE_NAME = "personnel"
REPORT_FILENAME = "finance_matrix_personnel_browser_report.json"
SUITE_TOTAL = len(PERSONNEL_MATRIX)
