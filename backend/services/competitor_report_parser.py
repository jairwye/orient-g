"""行业财报汇析 MD → CompetitorReportSnapshot（确定性解析，不用 LLM）。"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

PARSER_VERSION = "1.0.0"

ANCHOR_RE = re.compile(r"^#{1,3}\s+(sec-\d{2}(?:-\d+)?)\b\s*(.*)$", re.MULTILINE)
SECTION_ID_RE = re.compile(r"^(sec-\d{2})")
SEPARATOR_ROW_RE = re.compile(r"^[\s:\-|]+$")

COMPANY_LABELS = [
    ("yycq", "游艺春秋", "YYCQ"),
    ("37", "三七互娱", "三七互娱"),
    ("wm", "完美世界", "完美世界"),
    ("zq", "掌趣科技", "掌趣科技"),
    ("tr", "塔人网络", "塔人网络"),
    ("hq", "华清飞扬", "华清飞扬"),
    ("xs", "像素软件", "像素软件"),
    ("la", "绿岸网络", "绿岸网络"),
]

LABEL_TO_COMPANY: dict[str, tuple[str, str, str | None]] = {}
for cid, label, short in COMPANY_LABELS:
    LABEL_TO_COMPANY[label] = (cid, label, short)
    if short:
        LABEL_TO_COMPANY[short] = (cid, label, short)


class CompetitorParseError(ValueError):
    """阻断性解析错误。"""


def parse_markdown(
    md_text: str,
    *,
    source_filename: str,
    uploaded_by: str,
) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    if not md_text.strip():
        raise CompetitorParseError("文件为空")

    try:
        md_text.encode("utf-8")
    except UnicodeEncodeError as e:
        raise CompetitorParseError("文件须为 UTF-8 编码") from e

    meta = _parse_meta(md_text, source_filename, uploaded_by)
    matches = list(ANCHOR_RE.finditer(md_text))
    if not matches:
        raise CompetitorParseError("未找到 sec-XX 章节锚点")

    blocks_by_section: dict[str, list[dict[str, Any]]] = {}
    section_titles: dict[str, str] = {}

    for i, m in enumerate(matches):
        anchor = m.group(1)
        title_suffix = (m.group(2) or "").strip()
        sec_m = SECTION_ID_RE.match(anchor)
        if not sec_m:
            continue
        sec_id = sec_m.group(1)
        if re.fullmatch(r"sec-\d{2}", anchor) and title_suffix:
            section_titles[sec_id] = title_suffix
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(md_text)
        chunk = md_text[start:end]
        for block in _parse_chunk(chunk, anchor, warnings):
            blocks_by_section.setdefault(sec_id, []).append(block)

    sections: list[dict[str, Any]] = []
    missing: list[str] = []
    table_count = 0
    for n in range(1, 11):
        sid = f"sec-{n:02d}"
        blocks = blocks_by_section.get(sid, [])
        if not blocks:
            missing.append(sid)
        table_count += sum(1 for b in blocks if b.get("kind") == "table")
        sections.append(
            {
                "id": sid,
                "title": section_titles.get(sid, sid),
                "blocks": blocks,
            }
        )

    if missing:
        raise CompetitorParseError(f"缺少章节: {', '.join(missing)}")
    if table_count == 0:
        raise CompetitorParseError("未解析到任何表格")

    companies = _extract_companies(blocks_by_section, warnings)
    meta["company_count"] = len(companies)

    snapshot: dict[str, Any] = {
        "version": 1,
        "meta": meta,
        "companies": companies,
        "sections": sections,
        "warnings": warnings,
    }
    return snapshot, warnings


def _parse_meta(md_text: str, source_filename: str, uploaded_by: str) -> dict[str, Any]:
    title = "行业财报汇析"
    period = ""
    currency_unit = "万元"
    for line in md_text.splitlines()[:30]:
        s = line.strip()
        if s.startswith("# ") and not s.startswith("##"):
            title = s.lstrip("# ").strip()
        if "2025" in s and not period:
            m = re.search(r"(20\d{2})", s)
            if m:
                period = m.group(1)
        if "金额单位" in s or "万元" in s:
            if "万元" in s:
                currency_unit = "万元"
    return {
        "title": title,
        "period": period or "2025",
        "currency_unit": currency_unit,
        "company_count": 0,
        "source_filename": source_filename,
        "uploaded_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "uploaded_by": uploaded_by,
        "parser_version": PARSER_VERSION,
    }


def _parse_chunk(chunk: str, anchor: str, warnings: list[str]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    lines = chunk.splitlines()
    i = 0
    narrative_buf: list[str] = []

    def flush_narrative() -> None:
        nonlocal narrative_buf
        text = "\n".join(narrative_buf).strip()
        narrative_buf = []
        if not text:
            return
        lines = text.split("\n")
        while lines and lines[0].strip().startswith(">"):
            lines.pop(0)
        text = "\n".join(lines).strip()
        if not text:
            return
        blocks.append({"kind": "narrative", "anchor": anchor, "markdown": text})

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith("|"):
            flush_narrative()
            table_lines: list[str] = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i])
                i += 1
            table = _parse_table(table_lines, anchor, warnings)
            if table:
                blocks.append(table)
            continue
        narrative_buf.append(line)
        i += 1
    flush_narrative()
    return blocks


def _parse_table(
    table_lines: list[str],
    anchor: str,
    warnings: list[str],
) -> dict[str, Any] | None:
    if len(table_lines) < 2:
        return None
    rows_raw: list[list[str]] = []
    for line in table_lines:
        s = line.strip()
        if s.startswith("||"):
            s = "|" + s[2:]
        cells = [c.strip() for c in s.strip("|").split("|")]
        rows_raw.append(cells)

    header = rows_raw[0]
    body_start = 1
    if len(rows_raw) > 1 and _is_separator_row(rows_raw[1]):
        body_start = 2
    data_rows = rows_raw[body_start:]
    headers = [h for h in header if h]
    rows: list[dict[str, Any]] = []
    for row in data_rows:
        if len(row) < len(header):
            row = row + [""] * (len(header) - len(row))
        obj: dict[str, Any] = {}
        for h, c in zip(header, row):
            if not h:
                continue
            obj[h] = parse_cell_value(c, anchor, h, warnings)
        if any(v is not None and v != "" for v in obj.values()):
            rows.append(obj)
    if not rows:
        return None
    return {"kind": "table", "anchor": anchor, "headers": headers, "rows": rows}


def _is_separator_row(cells: list[str]) -> bool:
    joined = "".join(cells)
    return bool(joined) and SEPARATOR_ROW_RE.match(joined.replace(" ", ""))


def parse_cell_value(cell: str, anchor: str, header: str, warnings: list[str]) -> str | float | None:
    cell = cell.strip()
    if cell in ("", "—", "-", "–", "N/A", "n/a", "—"):
        return None
    dual = split_dual_values(cell)
    if dual is not None:
        warnings.append(f"{anchor} [{header}]: dual value '{cell}' → using first segment '{dual[0]}'")
        cell = dual[0]
    pct = cell.endswith("%")
    inner = cell.rstrip("%").strip()
    inner = inner.replace(",", "").replace("，", "")
    if inner.startswith("+"):
        inner = inner[1:]
    if inner.startswith("(") and inner.endswith(")"):
        inner = "-" + inner[1:-1]
    if re.match(r"^-?\d+(\.\d+)?$", inner):
        val = float(inner)
        return val / 100.0 if pct and val > 1 else (val if not pct else val / 100.0)
    if re.match(r"^-?\d+(\.\d+)?x$", inner, re.I):
        return float(inner[:-1])
    if re.match(r"^-?\d+(\.\d+)?$", inner.replace("亿", "").replace("万", "")):
        try:
            if "亿" in cell:
                return float(inner.replace("亿", "")) * 10000
            return float(inner.replace("万", ""))
        except ValueError:
            pass
    return cell


def split_dual_values(cell: str) -> tuple[str, str] | None:
    """启发式：'5698 289,895' → 两个数值片段。"""
    m = re.match(r"^([\d,.\-]+)\s+([\d,.\-]+)$", cell.strip())
    if not m:
        return None
    a, b = m.group(1), m.group(2)
    if _looks_numeric(a) and _looks_numeric(b):
        return a, b
    return None


def _looks_numeric(s: str) -> bool:
    s = s.replace(",", "").replace("，", "")
    return bool(re.match(r"^-?\d+(\.\d+)?%?$", s))


def _extract_companies(
    blocks_by_section: dict[str, list[dict[str, Any]]],
    warnings: list[str],
) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add_from_label(raw: str) -> None:
        key = raw.strip()
        if not key or key in ("公司", "指标", "科目", "排名"):
            return
        info = LABEL_TO_COMPANY.get(key)
        if info:
            cid, label, short = info
            if cid not in seen:
                seen.add(cid)
                entry: dict[str, Any] = {"id": cid, "label": label}
                if short and short != label:
                    entry["short"] = short
                found.append(entry)

    sec01 = blocks_by_section.get("sec-01", [])
    for block in sec01:
        if block.get("kind") != "table":
            continue
        if block.get("anchor") != "sec-01-2":
            continue
        for row in block.get("rows") or []:
            company_cell = row.get("公司")
            if isinstance(company_cell, str):
                add_from_label(company_cell)

    if len(found) < 8:
        for cid, label, short in COMPANY_LABELS:
            if cid not in seen:
                seen.add(cid)
                entry = {"id": cid, "label": label}
                if short and short != label:
                    entry["short"] = short
                found.append(entry)
        if len(found) >= 8:
            warnings.append("sec-01-2 公司列未完整识别，已回退默认 8 家列表")

    return found[:8]
