"""Docling 产物 → 纵向对比单公司结构（sections / blocks）。"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from backend.services.vertical_report_parser import (
    CANONICAL_PEER_IDS,
    _parse_company_body,
    _resolve_company_id,
)

MAIN_SECTION_RE = re.compile(r"^#{1,2}\s+([一二三四五六七八九十百]+[、．.].+?)\s*$")
SUBSECTION_RE = re.compile(r"^##\s+(.+?)\s*$")
DOC_H1_RE = re.compile(r"^#\s+(?!#)(.+?)\s*$")
NARRATIVE_SPLIT_RE = re.compile(r"(?<=\n)(?=\*\*[^*\n]+\*\*\s*$)", re.MULTILINE)
HEADING_LINE_RE = re.compile(r"^#{1,3}\s")
LIST_ITEM_LINE_RE = re.compile(r"^(?:\d+\.\s+\S|-\s)")
ORPHAN_NUMBER_LINE_RE = re.compile(r"^\d+\.\s*$")
TABLE_SEP_CELL_RE = re.compile(r"^:?-+:?$")
NARRATIVE_MARKER_RE = re.compile(r"^(?:洞察|总结|结论|概述)\s*[：:]")
DATA_CELL_HINT_RE = re.compile(r"\d|亿元|万元|%|元/|元\s*$")
# 表后/跨页 orphan 并入表格时，超过此长度的 narrative 不自动合并
ORPHAN_NARRATIVE_MAX_LEN = 24
# 跨页单元格续行（如「会计政策风险…」）允许更长的 suffix 合并
TABLE_CELL_SUFFIX_MAX_LEN = 96
# 三表分析等：Docling 丢表头时按列数回填
CANONICAL_FOUR_COL_REPORT_HEADER = [
    "报表项目",
    "本期(2025)",
    "上期(2024)",
    "关键风险/背离点",
]


def _split_pipe_row(line: str) -> list[str]:
    s = line.strip()
    if not s.startswith("|"):
        return []
    parts = [c.strip() for c in s.split("|")]
    if parts and parts[0] == "":
        parts = parts[1:]
    if parts and parts[-1] == "":
        parts = parts[:-1]
    return parts


def _join_pipe_row(cells: list[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def _append_last_table_cell(line: str, suffix: str) -> str:
    cells = _split_pipe_row(line)
    if not cells:
        return line.rstrip() + suffix
    cells[-1] = (cells[-1].rstrip() + suffix).strip()
    return _join_pipe_row(cells)


def _prepend_first_table_cell(line: str, prefix: str) -> str:
    cells = _split_pipe_row(line)
    if not cells:
        return prefix + line
    cells[0] = (prefix + cells[0].lstrip()).strip()
    return _join_pipe_row(cells)


RISK_ORPHAN_SPLIT_RE = re.compile(
    r"^(.+?风险)\s*(注.+?影响)\s*(\d{4}[，,].+)$"
)


def _append_orphan_to_table_row(line: str, orphan: str) -> str:
    """优先填入行内首个空列，否则拼到末列（跨页断行）。"""
    cells = _split_pipe_row(line)
    if not cells:
        return line.rstrip() + orphan
    for i, c in enumerate(cells):
        if not c.strip():
            cells[i] = orphan.strip()
            return _join_pipe_row(cells)
    cells[-1] = (cells[-1].rstrip() + orphan).strip()
    return _join_pipe_row(cells)


def _append_orphan_to_risk_table_row(line: str, orphan: str) -> str:
    """三列风险表：orphan 按 类别 / 描述续 / 具体内容续 拆分入格。"""
    cells = _split_pipe_row(line)
    if len(cells) != 3:
        return _append_orphan_to_table_row(line, orphan)
    compact = re.sub(r"\s+", " ", orphan.strip())
    m = RISK_ORPHAN_SPLIT_RE.match(compact)
    if not m:
        return _append_orphan_to_table_row(line, orphan)
    cells[0] = m.group(1).strip()
    cells[1] = (cells[1].rstrip() + m.group(2).strip()).strip()
    cells[2] = (cells[2].rstrip() + m.group(3).strip()).strip()
    return _join_pipe_row(cells)


def _append_orphan_to_table_row_smart(line: str, orphan: str) -> str:
    cells = _split_pipe_row(line)
    if len(cells) == 3 and not cells[0].strip():
        return _append_orphan_to_risk_table_row(line, orphan)
    return _append_orphan_to_table_row(line, orphan)


def _prepend_last_table_cell(line: str, prefix: str) -> str:
    cells = _split_pipe_row(line)
    if not cells:
        return prefix + line
    cells[-1] = (prefix + cells[-1].lstrip()).strip()
    return _join_pipe_row(cells)


def _is_table_separator_row(line: str) -> bool:
    cells = _split_pipe_row(line)
    if not cells:
        return False
    return all(not c or TABLE_SEP_CELL_RE.match(c.strip()) for c in cells)


def _peek_next_non_empty(lines: list[str], start: int) -> tuple[int, str] | None:
    for j in range(start, len(lines)):
        s = lines[j].strip()
        if s:
            return j, s
    return None


def _is_table_orphan_line(stripped: str) -> bool:
    if not stripped or stripped.startswith("|"):
        return False
    if HEADING_LINE_RE.match(stripped) or LIST_ITEM_LINE_RE.match(stripped):
        return False
    if ORPHAN_NUMBER_LINE_RE.match(stripped):
        return False
    if NARRATIVE_MARKER_RE.match(stripped):
        return False
    if stripped.startswith("**") and stripped.endswith("**"):
        return False
    if len(stripped) > TABLE_CELL_SUFFIX_MAX_LEN:
        return False
    if len(stripped) > ORPHAN_NARRATIVE_MAX_LEN and re.search(r"[。！？]", stripped):
        return False
    return True


def _last_table_line_index(lines: list[str]) -> int | None:
    for j in range(len(lines) - 1, -1, -1):
        if lines[j].strip().startswith("|"):
            return j
    return None


def repair_docling_markdown(md: str) -> str:
    """修复 Docling 表格断行、跨页拆表、孤立编号行等 MD 瑕疵。"""
    text = _nfkc((md or "").replace("\r\n", "\n"))
    lines = text.split("\n")
    out: list[str] = []
    table_tail_active = False
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        last_tbl_idx = _last_table_line_index(out) if table_tail_active else None

        if (
            last_tbl_idx is not None
            and _is_table_orphan_line(stripped)
        ):
            orphan_parts: list[str] = []
            while i < len(lines):
                s = lines[i].strip()
                if not s:
                    i += 1
                    nxt = _peek_next_non_empty(lines, i)
                    if orphan_parts and nxt and (
                        nxt[1].startswith("|") or HEADING_LINE_RE.match(nxt[1])
                    ):
                        break
                    if not nxt:
                        break
                    continue
                if not _is_table_orphan_line(s):
                    break
                orphan_parts.append(s)
                i += 1

            if orphan_parts:
                orphan = "".join(orphan_parts)
                nxt = _peek_next_non_empty(lines, i)
                if nxt and nxt[1].startswith("|"):
                    if len(orphan) > ORPHAN_NARRATIVE_MAX_LEN:
                        for part in orphan_parts:
                            out.append(part)
                        table_tail_active = False
                        continue
                    j = nxt[0]
                    table_lines: list[str] = []
                    while j < len(lines) and lines[j].strip().startswith("|"):
                        table_lines.append(lines[j])
                        j += 1
                    if table_lines:
                        target = 0
                        while target < len(table_lines) and _is_table_separator_row(table_lines[target]):
                            target += 1
                        if target < len(table_lines):
                            table_lines[target] = _prepend_last_table_cell(table_lines[target], orphan)
                        else:
                            table_lines[-1] = _append_last_table_cell(table_lines[-1], orphan)
                        table_lines = [ln for ln in table_lines if not _is_table_separator_row(ln)]
                        while out and not out[-1].strip():
                            out.pop()
                        out.extend(table_lines)
                        i = j
                        table_tail_active = True
                        continue
                tbl_idx = _last_table_line_index(out)
                if tbl_idx is not None:
                    if len(orphan) > TABLE_CELL_SUFFIX_MAX_LEN:
                        for part in orphan_parts:
                            out.append(part)
                        table_tail_active = False
                        continue
                    out[tbl_idx] = _append_orphan_to_table_row_smart(out[tbl_idx], orphan)
                table_tail_active = True
                continue

        out.append(line)
        if stripped.startswith("|"):
            table_tail_active = True
        elif stripped and (
            HEADING_LINE_RE.match(stripped)
            or LIST_ITEM_LINE_RE.match(stripped)
            or NARRATIVE_MARKER_RE.match(stripped)
            or (stripped.startswith("**") and stripped.endswith("**"))
            or len(stripped) > ORPHAN_NARRATIVE_MAX_LEN
        ):
            table_tail_active = False
        i += 1

    text = _collapse_blanks_within_tables("\n".join(out))
    text = _remove_empty_pipe_rows(text)
    return _strip_orphan_number_lines(text).strip()


def _collapse_blanks_within_tables(text: str) -> str:
    """去掉管道表行之间的空行，避免跨页续表被拆成多块。"""
    lines = text.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip() and out and out[-1].strip().startswith("|"):
            j = i
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines) and lines[j].strip().startswith("|"):
                i = j
                continue
        out.append(line)
        i += 1
    return "\n".join(out)


def _remove_empty_pipe_rows(text: str) -> str:
    """去掉 | | | 空表行（Docling 跨页常插入）。"""
    out: list[str] = []
    for line in text.split("\n"):
        if line.strip().startswith("|"):
            cells = _split_pipe_row(line)
            if cells and all(not c for c in cells):
                continue
        out.append(line)
    return "\n".join(out)


def _strip_orphan_number_lines(text: str) -> str:
    """去掉 Docling 在编号列表前多输出的孤立「1.」「2.」行。"""
    out: list[str] = []
    for line in text.split("\n"):
        if ORPHAN_NUMBER_LINE_RE.match(line.strip()):
            continue
        out.append(line)
    return "\n".join(out)


def clean_narrative_markdown(md: str) -> str:
    """叙事块内再清一遍孤立编号行、错位粗体短语与多余空行。"""
    text = _strip_orphan_number_lines(md or "")
    text = _repair_displaced_bold_phrases(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _repair_displaced_bold_phrases(text: str) -> str:
    """Docling 丢粗体且打乱语序时，仅还原语序（不注入 **，避免页内仅一段有粗体）。"""
    if not text or "结论" not in text:
        return text
    fixes: list[tuple[str, str]] = [
        (
            r"依然来自\s*,尤其以《([^》]+)》\s*核心贡献\s*游戏业务",
            r"核心贡献依然来自游戏业务，尤其以《\1》",
        ),
        (
            r"方面,\s*新业务\s*微短\s*和\s*已从探索",
            "微短剧和电竞国际化方面，新业务已从探索",
        ),
        (
            r"未⻅明显迹\s*剧\s*电竞国际化\s*潜在萎缩业务\s*象",
            "潜在萎缩业务未见明显迹象",
        ),
        (
            r"的\s*演进,新老业务协同发力,健康度与增⻓潜力均显著提\s*多元化、全球化结构\s*升",
            "的多元化、全球化结构演进，新老业务协同发力，健康度与增⻓潜力均显著提升",
        ),
    ]
    for pattern, repl in fixes:
        text = re.sub(pattern, repl, text)
    return text


HEADER_LABEL_HINT_RE = re.compile(
    r"指标|项目|类别|阶段|板块|区域|描述|产品|名称|报表|风险|内容|策略|贡献|类型|季度"
)


def _headers_look_like_data(headers: list[str]) -> bool:
    if not headers or not any(str(h or "").strip() for h in headers):
        return False
    nonempty = [str(h or "").strip() for h in headers if str(h or "").strip()]
    if any(HEADER_LABEL_HINT_RE.search(h) for h in nonempty):
        return False
    scored = sum(
        1
        for h in nonempty
        if re.search(r"\d+\.?\d*亿元", h)
        or (re.search(r"\d", h) and ("%" in h or re.search(r"\d+\.?\d*元", h)))
    )
    return scored >= max(1, len(nonempty) // 2)


def _row_dict_from_values(keys: list[str], values: list[str]) -> dict[str, str]:
    row: dict[str, str] = {}
    for i, key in enumerate(keys):
        row[key] = values[i] if i < len(values) else ""
    return row


def _remap_table_rows(rows: list[Any], old_keys: list[str], new_keys: list[str]) -> list[dict[str, str]]:
    remapped: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        values = [str(row.get(k, "")) for k in old_keys]
        remapped.append(_row_dict_from_values(new_keys, values))
    return remapped


def _fix_standalone_misheadered_table(block: dict[str, Any]) -> dict[str, Any]:
    headers = [str(h or "") for h in (block.get("headers") or [])]
    if not _headers_look_like_data(headers):
        return block
    n = len(headers)
    if n == 4:
        new_headers = list(CANONICAL_FOUR_COL_REPORT_HEADER)
    else:
        new_headers = [f"列{i + 1}" for i in range(n)]
    old_keys = block.get("header_keys") or headers
    mis_row = _row_dict_from_values(new_headers, headers)
    rows = _remap_table_rows(block.get("rows") or [], old_keys, new_headers)
    block["headers"] = new_headers
    block["header_keys"] = new_headers
    block["rows"] = [mis_row, *rows]
    return block


def _header_label(h: str) -> str:
    return (h or "").split("__")[0].strip()


def _merge_split_cell_values(values: list[str]) -> str:
    vals = [str(v).strip() for v in values if v is not None and str(v).strip()]
    if not vals:
        return ""
    if len(vals) == 1:
        return vals[0]
    if vals[0] == vals[1]:
        return vals[0]
    v0, v1 = vals[0], vals[1]
    if v1 in ("率)", "率）", "率", "长", "⻓"):
        return (v0.rstrip() + v1).replace(" ", "")
    if v0.endswith(("增长", "增⻓", "（", "(", "同", "净额同", "增⻓")):
        return (v0.rstrip() + v1.lstrip()).replace(" ", "")
    return vals[0] if len(v0) >= len(v1) else v1


def _collapse_duplicate_table_columns(block: dict[str, Any]) -> dict[str, Any]:
    """Docling 双列重复表头（指标|指标）或标签跨列拆开（增长|率））合并。"""
    headers = list(block.get("headers") or [])
    header_keys = list(block.get("header_keys") or headers)
    if len(header_keys) < 2:
        return block

    groups: list[tuple[str, list[int]]] = []
    i = 0
    while i < len(header_keys):
        label = _header_label(headers[i] if i < len(headers) else header_keys[i])
        idxs = [i]
        j = i + 1
        while j < len(header_keys):
            next_label = _header_label(headers[j] if j < len(headers) else header_keys[j])
            if next_label != label:
                break
            idxs.append(j)
            j += 1
        groups.append((label, idxs))
        i = j

    if all(len(g[1]) == 1 for g in groups):
        return block

    new_headers: list[str] = []
    new_keys: list[str] = []
    for label, idxs in groups:
        new_headers.append(label)
        new_keys.append(header_keys[idxs[0]].split("__")[0])

    new_rows: list[dict[str, Any]] = []
    for row in block.get("rows") or []:
        if not isinstance(row, dict):
            continue
        nr: dict[str, Any] = {}
        for (_, idxs), nk in zip(groups, new_keys):
            vals = [str(row.get(header_keys[k], "") or "") for k in idxs]
            nr[nk] = _merge_split_cell_values(vals)
        new_rows.append(nr)

    block["headers"] = new_headers
    block["header_keys"] = new_keys
    block["rows"] = new_rows
    return block


def _fix_risk_row_merged_category(block: dict[str, Any]) -> dict[str, Any]:
    """风险表末行 orphan 误入「风险类别」列时再拆分。"""
    keys = block.get("header_keys") or []
    if len(keys) < 3 or _header_label(str(keys[0])) != "风险类别":
        return block
    cat_k, desc_k, detail_k = keys[0], keys[1], keys[2]
    for row in block.get("rows") or []:
        if not isinstance(row, dict):
            continue
        cat = str(row.get(cat_k) or "")
        if "注" not in cat or "风险" not in cat:
            continue
        compact = re.sub(r"\s+", " ", cat.strip())
        m = RISK_ORPHAN_SPLIT_RE.match(compact)
        if not m:
            continue
        row[cat_k] = m.group(1).strip()
        row[desc_k] = (str(row.get(desc_k) or "").rstrip() + " " + m.group(2).strip()).strip()
        row[detail_k] = (str(row.get(detail_k) or "").rstrip() + " " + m.group(3).strip()).strip()
    return block


def _normalize_table_block(block: dict[str, Any]) -> dict[str, Any]:
    block = _collapse_duplicate_table_columns(block)
    block = _fix_risk_row_merged_category(block)
    return block


def _merge_misheadered_tables(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """跨页续表首行被误当表头时，并回上一张表或补标准表头。"""
    out: list[dict[str, Any]] = []
    for block in blocks:
        if block.get("kind") != "table":
            out.append(block)
            continue
        headers = [str(h or "") for h in (block.get("headers") or [])]
        if _headers_look_like_data(headers) and out and out[-1].get("kind") == "table":
            prev = out[-1]
            prev_headers = prev.get("headers") or []
            if (
                len(prev_headers) == len(headers)
                and prev_headers
                and not _headers_look_like_data(prev_headers)
            ):
                header_keys = prev.get("header_keys") or prev_headers
                prev_rows = list(prev.get("rows") or [])
                prev_rows.append(_row_dict_from_values(header_keys, headers))
                old_keys = block.get("header_keys") or headers
                prev_rows.extend(_remap_table_rows(block.get("rows") or [], old_keys, header_keys))
                prev["rows"] = prev_rows
                continue
        if _headers_look_like_data(headers):
            block = _fix_standalone_misheadered_table(block)
        out.append(block)
    return out


def _nfkc(text: str) -> str:
    t = unicodedata.normalize("NFKC", text)
    return t.replace("⻛", "风")


def normalize_docling_markdown(md: str) -> str:
    """Docling MD：repair + NFKC + 主节 ### 一、… + 子节 **亮点** 等。"""
    text = repair_docling_markdown(md)
    if not text:
        return ""

    lines: list[str] = []
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            lines.append("")
            continue
        m_main = MAIN_SECTION_RE.match(stripped)
        if m_main:
            lines.append(f"### {m_main.group(1).strip()}")
            continue
        m_sub = SUBSECTION_RE.match(stripped)
        if m_sub:
            title = m_sub.group(1).strip()
            lines.append("")
            lines.append(f"**{title}**")
            lines.append("")
            continue
        m_h1 = DOC_H1_RE.match(stripped)
        if m_h1:
            lines.append(m_h1.group(1).strip())
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _split_narrative_subsections(markdown: str) -> list[str]:
    """按 **子标题** 拆成多个 narrative 块（如第四节内 亮点 / 风险点）。"""
    text = markdown.strip()
    if not text:
        return []
    parts = [p.strip() for p in NARRATIVE_SPLIT_RE.split(text) if p.strip()]
    return parts if parts else [text]


def _merge_orphan_narratives_into_tables(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """表后极短 orphan narrative（如「成能力」）并回上一表末格。"""
    out: list[dict[str, Any]] = []
    for block in blocks:
        if block.get("kind") == "narrative":
            md = str(block.get("markdown") or "").strip()
            compact = md.replace("\n", "").replace(" ", "")
            if (
                compact
                and len(compact) <= ORPHAN_NARRATIVE_MAX_LEN
                and out
                and out[-1].get("kind") == "table"
                and not re.search(r"[。！？；]", compact)
            ):
                tbl = out[-1]
                rows = tbl.get("rows") or []
                keys = tbl.get("header_keys") or tbl.get("headers") or []
                if rows and keys:
                    last_key = keys[-1]
                    last_row = rows[-1]
                    if isinstance(last_row, dict):
                        prev = str(last_row.get(last_key) or "")
                        last_row[last_key] = (prev.rstrip() + compact).strip()
                continue
        out.append(block)
    return out


def _is_separator_data_row(row: dict[str, Any]) -> bool:
    cells = [str(v or "").strip() for v in row.values() if str(v or "").strip()]
    if not cells:
        return True
    return all(re.match(r"^-+$", c.replace(" ", "")) for c in cells)


def _strip_separator_data_rows(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for block in blocks:
        if block.get("kind") != "table":
            continue
        rows = block.get("rows") or []
        block["rows"] = [r for r in rows if isinstance(r, dict) and not _is_separator_data_row(r)]
    return blocks


def _postprocess_section_blocks(sections: list[dict[str, Any]]) -> None:
    for sec in sections:
        blocks = sec.get("blocks") or []
        blocks = _merge_misheadered_tables(blocks)
        for i, block in enumerate(blocks):
            if block.get("kind") == "table":
                blocks[i] = _normalize_table_block(block)
        blocks = _strip_separator_data_rows(blocks)
        blocks = _merge_orphan_narratives_into_tables(blocks)
        for block in blocks:
            if block.get("kind") == "narrative":
                block["markdown"] = clean_narrative_markdown(str(block.get("markdown") or ""))
        sec["blocks"] = blocks


def _expand_section_narratives(sections: list[dict[str, Any]]) -> None:
    for sec in sections:
        expanded: list[dict[str, Any]] = []
        for block in sec.get("blocks") or []:
            if block.get("kind") != "narrative":
                expanded.append(block)
                continue
            md = str(block.get("markdown") or "").strip()
            chunks = _split_narrative_subsections(md)
            for chunk in chunks:
                expanded.append({**block, "markdown": chunk})
        sec["blocks"] = expanded


def _table_block_from_docling_grid(
    grid: list[list[Any]],
    anchor: str,
    warnings: list[str],
) -> dict[str, Any] | None:
    if not grid or len(grid) < 2:
        return None
    header_row = [str(c or "").strip() for c in grid[0]]
    if not any(header_row):
        warnings.append(f"{anchor}: Docling 表首行为空")
        return None
    rows: list[dict[str, str]] = []
    for row in grid[1:]:
        cells = [str(c or "").strip() for c in row]
        while len(cells) < len(header_row):
            cells.append("")
        cells = cells[: len(header_row)]
        rows.append({header_row[i] or f"col_{i}": cells[i] for i in range(len(header_row))})
    return {
        "kind": "table",
        "anchor": anchor,
        "headers": header_row,
        "header_keys": header_row,
        "rows": rows,
    }


def _extract_tables_from_docling_json(doc: dict[str, Any], anchor: str, warnings: list[str]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    tables = doc.get("tables")
    if not isinstance(tables, list):
        return blocks
    for ti, tbl in enumerate(tables):
        if not isinstance(tbl, dict):
            continue
        data = tbl.get("data") if isinstance(tbl.get("data"), dict) else tbl
        grid = data.get("grid") if isinstance(data, dict) else None
        if isinstance(grid, list) and grid:
            block = _table_block_from_docling_grid(grid, f"{anchor}-t{ti + 1}", warnings)
            if block:
                blocks.append(block)
            continue
        # Docling table_cells 格式
        cells = data.get("table_cells") if isinstance(data, dict) else None
        if isinstance(cells, list) and cells:
            by_row: dict[int, dict[int, str]] = {}
            max_col = 0
            for cell in cells:
                if not isinstance(cell, dict):
                    continue
                r = int(cell.get("start_row_offset_idx") or cell.get("row") or 0)
                c = int(cell.get("start_col_offset_idx") or cell.get("col") or 0)
                txt = str(cell.get("text") or "").strip()
                by_row.setdefault(r, {})[c] = txt
                max_col = max(max_col, c)
            if by_row:
                row_keys = sorted(by_row.keys())
                grid2 = []
                for rk in row_keys:
                    grid2.append([by_row[rk].get(ci, "") for ci in range(max_col + 1)])
                block = _table_block_from_docling_grid(grid2, f"{anchor}-t{ti + 1}", warnings)
                if block:
                    blocks.append(block)
    return blocks


def company_from_docling(
    *,
    company_id: str,
    company_name: str,
    company_index: int,
    md_text: str,
    json_path: Path | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """单公司 Docling 输出 → vertical company 节点。"""
    w = warnings if warnings is not None else []
    cid = company_id if company_id in CANONICAL_PEER_IDS else _resolve_company_id(company_index)
    snap_id = f"v-{cid}"
    body = normalize_docling_markdown(md_text)
    if not body:
        w.append(f"{company_name}: Docling MD 为空")
        body = "（暂无正文）"

    sections = _parse_company_body(body, snap_id, w)
    _postprocess_section_blocks(sections)
    _expand_section_narratives(sections)
    flat_blocks: list[dict[str, Any]] = []
    for sec in sections:
        flat_blocks.extend(sec.get("blocks") or [])

    if json_path and json_path.is_file():
        try:
            doc = json.loads(json_path.read_text(encoding="utf-8"))
            json_tables = _extract_tables_from_docling_json(doc, snap_id, w)
            md_table_count = sum(1 for b in flat_blocks if b.get("kind") == "table")
            if len(json_tables) > md_table_count:
                # JSON 表更完整时，替换 MD 解析的 table blocks，保留 narrative
                narratives = [b for b in flat_blocks if b.get("kind") != "table"]
                flat_blocks = narratives + json_tables
                if sections:
                    sections[-1]["blocks"] = (sections[-1].get("blocks") or [])
                    sec_narr = [b for b in sections[-1]["blocks"] if b.get("kind") != "table"]
                    sections[-1]["blocks"] = sec_narr + json_tables
        except Exception as exc:
            w.append(f"{company_name}: Docling JSON 解析失败 ({exc})")

    return {
        "id": cid,
        "snap_id": snap_id,
        "name": company_name,
        "sections": sections,
        "blocks": flat_blocks,
    }


def build_vertical_snapshot(
    companies: list[dict[str, Any]],
    *,
    title: str = "各公司纵向对比",
    source: str = "docling",
    uploaded_by: str = "",
    uploaded_at: str = "",
    source_filename: str = "",
    parser_version: str = "1.2.0-docling",
) -> dict[str, Any]:
    warnings: list[str] = []
    for co in companies:
        warnings.extend(co.pop("_warnings", []) or [])
    return {
        "version": 1,
        "meta": {
            "title": title,
            "parser_version": parser_version,
            "company_count": len(companies),
            "data_source": source,
            "uploaded_by": uploaded_by,
            "uploaded_at": uploaded_at,
            "source_filename": source_filename,
        },
        "intro": [],
        "companies": companies,
        "warnings": warnings,
    }


def merged_markdown_from_companies(companies: list[dict[str, Any]], title: str) -> str:
    """导出合并 MD（供人工 diff / 覆写上传）。"""
    parts = [f"# {title}", ""]
    for i, co in enumerate(companies, start=1):
        parts.append(f"## {i}. {co.get('name') or co.get('id')}")
        parts.append("")
        for sec in co.get("sections") or []:
            st = sec.get("title") or ""
            if st and st != "正文":
                parts.append(f"### {st}")
                parts.append("")
            for block in sec.get("blocks") or []:
                if block.get("kind") == "narrative":
                    parts.append(str(block.get("markdown") or ""))
                    parts.append("")
                elif block.get("kind") == "table":
                    headers = block.get("headers") or []
                    rows = block.get("rows") or []
                    if headers:
                        parts.append("| " + " | ".join(headers) + " |")
                        parts.append("| " + " | ".join(["---"] * len(headers)) + " |")
                        for row in rows:
                            if isinstance(row, dict):
                                parts.append("| " + " | ".join(str(row.get(h, "")) for h in headers) + " |")
                        parts.append("")

    return "\n".join(parts).strip() + "\n"
