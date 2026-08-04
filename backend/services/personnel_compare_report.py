"""人员结构横比：结构化成稿（对比表 + 口径 + 证据约束分析）。"""

from __future__ import annotations

import re
from typing import Any

_AMOUNT_RE = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d{2})?|\d+\.\d{2}")
_RD_COUNT_RE = re.compile(
    r"研发人员(?:数量|合计)?[^0-9]{0,24}(\d{1,3}(?:,\d{3})*|\d+)\s*人?",
    re.I,
)
_RD_SHARE_RE = re.compile(r"研发人员(?:数量)?占比[^0-9]{0,16}(\d+(?:\.\d+)?)\s*%", re.I)
_EXCEL_RD_RE = re.compile(r"研发[^\n|]{0,20}\|\s*(\d+(?:\.\d{2})?)", re.I)
_HEADCOUNT_RE = re.compile(r"在职员工[^0-9]{0,20}(\d+)\s*人", re.I)

_NOISE_PAT = re.compile(
    r"连带责任保证|营业收入合计|货币资金|筹资活动|投资活动",
    re.I,
)


_EXCEL_CAT_ROW = re.compile(
    r"\|\s*[^|]*\|\s*[^|]*\|\s*[^|]*\|\s*[^|]*\|\s*[^|]*\|\s*(运营|管理|研发|支持)\s*\|\s*[^|]*\|\s*(\d+(?:\.\d{2})?)\s*\|",
    re.I,
)
_ROLE_COUNT_RE = re.compile(
    r"(销售|技术|财务|行政|管理|运营|生产)人员?\s*[（(]?[^0-9]{0,12}[）)]?\s*(\d{1,3}(?:,\d{3})*|\d+)\s*人",
    re.I,
)
_ROLE_TABLE_ROW_RE = re.compile(
    r"\|\s*((?:销售|技术|财务|行政|管理|运营|研发|教研)人员(?:\s+其他职能部门人员)?)\s*\|\s*"
    r"(\d{1,3}(?:,\d{3})*|\d+(?:\s+\d+)?)\s*\|",
    re.I,
)
_ROLE_LABEL_TO_ROW = {
    "销售人员": "销售",
    "运营人员": "运营",
    "行政人员": "管理",
    "管理人员": "管理",
    "技术人员": "支持",
    "教研人员": "支持",
}
_STRUCTURE_TABLE_TITLE = "人员结构对照"
_EXCEL_ROW_RD = re.compile(
    r"^\|\s*[^|]*\|\s*[^|]*\|\s*[^|]*\|\s*[^|]*\|\s*[^|]*\|\s*研发\s*\|\s*[^|]*\|\s*(\d+(?:\.\d{2})?)\s*\|",
    re.I | re.M,
)


def _fmt_count(raw: str | float | None) -> str:
    if raw is None or raw == "":
        return "—"
    if isinstance(raw, float):
        return str(int(raw)) if raw == int(raw) else f"{raw:.2f}"
    s = str(raw).replace(",", "").strip()
    try:
        v = float(s)
        return str(int(v)) if v == int(v) else f"{v:.2f}"
    except ValueError:
        return str(raw)


def _parse_excel_personnel_breakdown(text: str) -> dict[str, float]:
    """1.1信息-人员：一级归属 → 人数。"""
    out: dict[str, float] = {}
    t = text or ""
    for m in _EXCEL_CAT_ROW.finditer(t):
        out[m.group(1).strip()] = float(m.group(2))
    for line in t.splitlines():
        if "|" not in line or not any(c in line for c in ("运营", "管理", "研发", "支持")):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        cat = next((c for c in cells if c in ("运营", "管理", "研发", "支持")), "")
        if not cat or cat in out:
            continue
        for cell in reversed(cells):
            m = re.fullmatch(r"(\d+(?:\.\d{2})?)", cell)
            if m:
                out[cat] = float(m.group(1))
                break
    for line in t.splitlines():
        m = re.match(r"^(运营|管理|研发|支持)\s*\|\s*(\d+(?:\.\d{2})?)\s*$", line.strip())
        if m:
            out[m.group(1)] = float(m.group(2))
    return out


def _parse_role_breakdown(text: str) -> dict[str, int]:
    """年报正文：销售/技术等职能人数（若节选含）。"""
    out: dict[str, int] = {}
    for m in _ROLE_COUNT_RE.finditer(text or ""):
        role = m.group(1)
        n = int(m.group(2).replace(",", ""))
        if n >= 2:
            out[role] = n
    for m in _ROLE_TABLE_ROW_RE.finditer(text or ""):
        raw_label = m.group(1).strip()
        nums = [int(x.replace(",", "")) for x in re.findall(r"\d{1,3}(?:,\d{3})*|\d+", m.group(2))]
        if "运营人员" in raw_label and "其他职能部门人员" in raw_label and len(nums) >= 2:
            if nums[0] >= 2:
                out["运营"] = nums[0]
            if nums[1] >= 2:
                out.setdefault("支持", nums[1])
            continue
        row_role = _ROLE_LABEL_TO_ROW.get(raw_label.split()[0])
        if not row_role or row_role == "研发":
            continue
        if nums and nums[0] >= 2:
            out[row_role] = nums[0]
    for line in (text or "").splitlines():
        if "|" not in line:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        raw = cells[0]
        row_role = _ROLE_LABEL_TO_ROW.get(raw) or (
            raw if raw in ("销售", "技术", "财务", "行政", "管理", "运营", "生产") else ""
        )
        if not row_role or row_role == "研发":
            continue
        for cell in cells[1:]:
            m = re.fullmatch(r"(\d{1,3}(?:,\d{3})*|\d+)", cell.replace(",", ""))
            if m:
                n = int(m.group(1).replace(",", ""))
                if n >= 2:
                    out[row_role] = n
                break
    return out


def sanqi_staff_roles_missing(excerpts: list[dict[str, str]]) -> bool:
    """可比公司A侧除研发外是否仍缺职能分项（需补检索员工情况）。"""
    sanqi_text = next(
        (str(ex.get("excerpt") or "") for ex in excerpts if "可比公司A" in str(ex.get("entity") or "")),
        "",
    )
    if not sanqi_text:
        return True
    roles = _parse_role_breakdown(sanqi_text)
    if roles.get("销售") or roles.get("运营"):
        return False
    non_rd = {k: v for k, v in roles.items() if k != "研发"}
    return len(non_rd) < 1


def _parse_rd_education_age(text: str) -> tuple[dict[str, str], dict[str, str]]:
    edu: dict[str, str] = {}
    age: dict[str, str] = {}
    t = text or ""
    for label in ("本科", "硕士", "大专及以下", "博士"):
        m = re.search(rf"\|\s*{re.escape(label)}\s*\|\s*(\d{{1,3}}(?:,\d{{3}})*|\d+)", t)
        if m:
            edu[label] = m.group(1).replace(",", "")
    for label in ("30岁以下", "30~40岁", "40岁以上"):
        m = re.search(rf"\|\s*{re.escape(label)}\s*\|\s*(\d{{1,3}}(?:,\d{{3}})*|\d+)", t)
        if m:
            age[label] = m.group(1).replace(",", "")
    return edu, age


def _excel_rd_count_from_table(text: str) -> str | None:
    """1.1信息-人员 excel 表：取「一级人员归属=研发」行的「人数」列（避免 1.10 编码误匹配为 1）。"""
    t = text or ""
    best: float | None = None
    for m in _EXCEL_ROW_RD.finditer(t):
        v = float(m.group(1))
        if v >= 2 and (best is None or v > best):
            best = v
    for line in t.splitlines():
        if "|" not in line or "研发" not in line:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not any(c == "研发" for c in cells):
            continue
        for cell in reversed(cells):
            m = re.fullmatch(r"(\d+(?:\.\d{2})?)", cell)
            if not m:
                continue
            v = float(m.group(1))
            if v >= 2 and (best is None or v > best):
                best = v
            break
    if best is None:
        return None
    return str(int(best)) if best == int(best) else str(best)


def _extract_entity_metrics(excerpt: str, *, entity: str) -> dict[str, str]:
    t = excerpt or ""
    out: dict[str, str] = {"entity": entity}
    if "1.1信息-人员" in t:
        out["source"] = "excel·1.1信息-人员"
        excel_rd = _excel_rd_count_from_table(t)
        if excel_rd:
            out["rd_count"] = excel_rd
    elif "研发人员情况" in t:
        out["source"] = "年报·研发人员情况"
    else:
        out["source"] = "知识库节选"
    m = _RD_COUNT_RE.search(t)
    if m and "rd_count" not in out:
        out["rd_count"] = m.group(1).replace(",", "")
    m = _RD_SHARE_RE.search(t)
    if m:
        out["rd_share_pct"] = m.group(1)
    if "rd_count" not in out:
        m = _EXCEL_RD_RE.search(t)
        if m:
            v = float(m.group(1))
            if v >= 2:
                out["rd_count"] = str(int(v)) if v == int(v) else m.group(1)
    m = _HEADCOUNT_RE.search(t)
    if m:
        out["headcount"] = m.group(1)
    return out


def personnel_compare_hermes_draft_is_bad(text: str, *, user_query: str) -> bool:
    """Hermes 过程稿/错稿：旧模板、研发=1、缺人员结构对照等。"""
    from backend.services.kb_ask_mcp_reply import personnel_compare_reply_misattributed
    from backend.services.kb_retrieval_plan import query_wants_personnel_compare

    uq = (user_query or "").strip()
    if not query_wants_personnel_compare(uq):
        return False
    h = (text or "").strip()
    if not h:
        return False
    if len(h) < 40 and "核心指标对照" not in h and "人员结构对照" not in h:
        return False
    if personnel_compare_reply_misattributed(h, user_query=uq):
        return True
    if personnel_compare_needs_structured_gate(h, user_query=uq):
        return True
    if re.search(r"核心指标对照|核心指标对比", h):
        return True
    if re.search(r"一、(?:总体)?规模|规模对比|总体规模", h):
        return True
    if re.search(r"22\.6\s*倍|14\.5\s*倍|约为YYCQ的\d+", h):
        return True
    if re.search(r"\|\s*研发人员\s*\|\s*95\s*人\s*\|", h):
        return True
    if re.search(r"excel[^|\n]{0,48}研发[^|\n]{0,24}\|\s*1\s*\|", h, re.I):
        return True
    if re.search(r"\|\s*YYCQ[^\n|]{0,40}\|\s*1\s*\|", h):
        return True
    if re.search(r"研发[/／]分项人数[^|\n]{0,24}\|\s*1\s*\|", h):
        return True
    return False


def personnel_compare_sanqi_table_incomplete(text: str) -> bool:
    """对照表已有，但可比公司A销售/运营等仍「证据未覆盖」。"""
    h = (text or "").strip()
    if _STRUCTURE_TABLE_TITLE not in h:
        return False
    if re.search(r"\|\s*销售\s*\|[^|\n]*证据未覆盖", h):
        return True
    if re.search(r"\|\s*运营\s*\|[^|\n]*证据未覆盖", h):
        return True
    return False


_ORIENTG_TEMPLATE_MARKERS = (
    r"\*\*结论\*\*：以下按\*\*职能归属/人员分项\*\*对比",
    r"以上数据均来自当前知识库\s*citations\s*节选",
    r"YYCQ vs 可比公司A\s*·\s*2025\s*人员结构对比",
)


def looks_like_orientg_personnel_template(text: str) -> bool:
    """Orient-G `format_personnel_compare_structured_report` 固定套话指纹（anti-gate 验收）。"""
    h = (text or "").strip()
    if not h:
        return False
    hits = sum(1 for pat in _ORIENTG_TEMPLATE_MARKERS if re.search(pat, h))
    # 标题 + 至少一条结语/结论套话，避免误伤 Hermes 自拟标题
    if hits >= 2:
        return True
    if re.search(_ORIENTG_TEMPLATE_MARKERS[0], h) and re.search(_ORIENTG_TEMPLATE_MARKERS[1], h):
        return True
    return False


def personnel_compare_needs_structured_gate(text: str, *, user_query: str) -> bool:
    """横比终稿缺结构化成稿段（人员结构对照）时须走 final gate。"""
    from backend.services.kb_retrieval_plan import (
        extract_query_entity_phrases,
        query_wants_personnel_compare,
        query_wants_personnel_structure,
    )

    uq = (user_query or "").strip()
    h = (text or "").strip()
    if not h or not query_wants_personnel_structure(uq):
        return False
    if len(extract_query_entity_phrases(uq)) < 2:
        return False
    if query_wants_personnel_compare(uq) and personnel_compare_sanqi_table_incomplete(h):
        return True
    if _STRUCTURE_TABLE_TITLE in h and "### 对比分析" in h and not personnel_excerpt_dump_only(h):
        return False
    if _STRUCTURE_TABLE_TITLE in h and "对比分析" in h and not personnel_excerpt_dump_only(h):
        return False
    return True


def personnel_excerpt_dump_only(text: str) -> bool:
    """终稿是否仅为双主体 excerpt 粘贴（无分析段）。"""
    h = (text or "").strip()
    if not h:
        return True
    if _NOISE_PAT.search(h):
        return True
    has_analysis = bool(
        re.search(
            r"#+\s*对比分析|结构差异|口径差异|不可直接|主要差异|对比要点",
            h,
            re.I,
        )
    )
    if has_analysis:
        return False
    if "以下对比基于知识库" in h and "对比说明" in h and len(h) < 2200:
        return True
    return False


def personnel_reply_has_analysis(text: str, *, min_len: int = 500) -> bool:
    h = (text or "").strip()
    if ("### 对比分析" in h and _STRUCTURE_TABLE_TITLE in h) or (
        "对比分析" in h and _STRUCTURE_TABLE_TITLE in h
    ):
        if len(h) >= 120 and not _NOISE_PAT.search(h):
            if re.search(r"运营|管理|支持|职能|分项", h):
                return True
    if len(h) < min_len:
        return False
    if personnel_excerpt_dump_only(h):
        return False
    if _NOISE_PAT.search(h):
        return False
    return bool(
        re.search(
            r"对比分析|结构差异|口径|人员结构|1\.1信息-人员|主要差异|结论",
            h,
            re.I,
        )
    )


def _sanqi_cell(
    role: str,
    *,
    metrics: dict[str, str],
    roles: dict[str, int],
) -> str:
    if role == "研发":
        rd = metrics.get("rd_count")
        if not rd:
            return "证据未覆盖"
        share = metrics.get("rd_share_pct")
        return f"{rd} 人（占员工 {share}%）" if share else f"{rd} 人"
    if role == "销售" and roles.get("销售"):
        return f"{roles['销售']} 人"
    if role in roles:
        return f"{roles[role]} 人"
    return "证据未覆盖（节选无该分项）"


def _yycq_cell(role: str, breakdown: dict[str, float]) -> str:
    if role in breakdown:
        return f"{_fmt_count(breakdown[role])} 人"
    return "证据未覆盖"


def format_personnel_compare_structured_report(
    excerpts: list[dict[str, str]],
    *,
    user_query: str = "",
) -> str | None:
    """人员结构横比：职能分项对照表 + 研发结构 + 分析（非仅研发人数）。"""
    if len(excerpts) < 2:
        return None

    by_ent: dict[str, str] = {}
    for ex in excerpts:
        ent = str(ex.get("entity") or "").strip()
        if ent:
            by_ent[ent] = str(ex.get("excerpt") or "")

    sanqi_text = next((t for e, t in by_ent.items() if "可比公司A" in e), excerpts[0].get("excerpt", ""))
    yycq_text = next((t for e, t in by_ent.items() if "YYCQ" in e), excerpts[1].get("excerpt", ""))

    sanqi_m = _extract_entity_metrics(str(sanqi_text), entity="可比公司A")
    yycq_m = _extract_entity_metrics(str(yycq_text), entity="YYCQ")
    yycq_bd = _parse_excel_personnel_breakdown(str(yycq_text))
    sanqi_roles = _parse_role_breakdown(str(sanqi_text))
    sanqi_edu, sanqi_age = _parse_rd_education_age(str(sanqi_text))

    row_roles = ["研发", "运营", "管理", "支持", "销售"]
    if not any(r in yycq_bd for r in ("运营", "管理", "支持")):
        row_roles = ["研发", "运营", "管理", "支持", "销售"]

    parts = [
        "## YYCQ vs 可比公司A · 2025 人员结构对比",
        "",
        "**结论**：以下按**职能归属/人员分项**对比 2025 年人员结构；研发仅为其中一个维度。"
        "两家数据来源与统计口径不同，**不可**将YYCQ excel 分项合计与可比公司A员工总数直接比规模。",
        "",
        f"### {_STRUCTURE_TABLE_TITLE}",
        "",
        "| 职能归属 | 可比公司A | YYCQ |",
        "| --- | --- | --- |",
    ]

    for role in row_roles:
        if role not in yycq_bd and role not in ("研发", "销售"):
            if role in ("运营", "管理", "支持") and not yycq_bd:
                continue
        parts.append(
            f"| {role} | {_sanqi_cell(role, metrics=sanqi_m, roles=sanqi_roles)} | {_yycq_cell(role, yycq_bd)} |"
        )

    if yycq_bd:
        total = sum(yycq_bd.values())
        parts.append(f"| **分项合计** | — | **{_fmt_count(total)} 人**（excel 四项加总） |")

    parts.extend(
        [
            "",
            "*口径：可比公司A为年报节选（研发人员情况 + 员工数量/专业构成）；"
            "YYCQ为 excel「1.1信息-人员」一级归属分项。*",
            "",
        ]
    )

    if sanqi_edu or sanqi_age:
        parts.extend(["### 可比公司A · 研发人员学历/年龄（年报节选）", ""])
        if sanqi_edu:
            edu_line = "、".join(f"{k} {v} 人" for k, v in sanqi_edu.items())
            parts.append(f"- **学历**：{edu_line}。")
        if sanqi_age:
            age_line = "、".join(f"{k} {v} 人" for k, v in sanqi_age.items())
            parts.append(f"- **年龄**：{age_line}。")
        parts.append("")

    parts.extend(["### 对比分析", ""])

    if yycq_bd:
        top = max(yycq_bd.items(), key=lambda x: x[1])
        rd_n = yycq_bd.get("研发", 0)
        total = sum(yycq_bd.values()) or 1
        parts.append(
            f"- **YYCQ**：excel 呈现运营/管理/研发/支持四分项；"
            f"最大单项为**{top[0]} {_fmt_count(top[1])} 人**；"
            f"研发 {_fmt_count(rd_n)} 人，约占分项合计 {rd_n / total * 100:.1f}%。"
        )
    else:
        parts.append("- **YYCQ**：证据节选含 1.1信息-人员表，详见下节。")

    if sanqi_m.get("rd_count"):
        line = f"- **可比公司A**：年报研发人员 **{sanqi_m['rd_count']}** 人"
        if sanqi_m.get("rd_share_pct"):
            line += f"（占员工 {sanqi_m['rd_share_pct']}%）"
        if sanqi_roles:
            extras = "、".join(f"{k}{v}人" for k, v in sorted(sanqi_roles.items()))
            line += f"；节选另含职能分项：{extras}"
        elif not sanqi_roles:
            line += "；销售/运营等职能分项未进入当前 citations 节选"
        line += "。"
        parts.append(line)

    parts.extend(
        [
            "- **结构差异**：YYCQ为内部 excel 职能四分项（偏精简团队）；"
            "可比公司A年报另披露销售/运营/技术等专业构成，与YYCQ「一级归属」口径不完全一一对应。",
            "- **可比性**：仅研发维度可做「占比/规模」参照；全口径人员结构对比须两边同口径披露，缺失写「证据未覆盖」。",
            "",
            "以上数据均来自当前知识库 citations 节选，口径见各主体 section 标题。",
            "",
        ]
    )
    return "\n".join(parts).strip() + "\n"
