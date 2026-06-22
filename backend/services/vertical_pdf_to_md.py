"""纵向分析 PDF → Markdown：段落 reflow + 基于坐标的表格重建。"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Sequence

try:
    import pdfplumber
except ImportError as exc:  # pragma: no cover
    raise ImportError("需要 pdfplumber：pip install pdfplumber") from exc

NUMERIC_CELL_RE = re.compile(r"^-?[+]?\d[\d,]*(?:\.\d+)?(?:%|亿元|亿|元|pct)?$")
SECTION_START_RE = re.compile(
    r"^([一二三四五六七八九十]+[、．.]|[#＃]?第[0-9一二三四五六七八九十]+[章节部分篇]|"
    r"表\s*\d+[：:]|洞察[：:]|结论[：:]|亮点总结|风险总结|"
    r"注[：:])"
)
LIST_ITEM_RE = re.compile(r"^\d{1,2}\.(?!\d)")
BULLET_RE = re.compile(r"^[·•]")
# 纵向报告主节标题：一、… 十八、…（不含亮点总结/洞察等子标题）
MAIN_SECTION_HEADING_RE = re.compile(r"^[一二三四五六七八九十百]+[、．.]")


def _normalize_text(text: str) -> str:
    """PDF 常含兼容区字形（如 ⼀），NFKC 便于章节/列表正则匹配。"""
    t = unicodedata.normalize("NFKC", text)
    return t.replace("⻛", "风")


def _is_product_row(cells: list[str]) -> bool:
    if not cells:
        return False
    first = cells[0].strip()
    return first.startswith("《") or first.startswith("储备")


def _is_lifecycle_fragment(text: str) -> bool:
    t = text.strip()
    if not t:
        return False
    if re.search(r"(导入|成长|成熟|筹备)期", t):
        return True
    if re.search(r"(入榜|收入榜|生命周期|长线)", t):
        return True
    if len(t) <= 8 and t.endswith("期"):
        return True
    return False


@dataclass
class PdfLine:
    y: float
    cells: list[str]

    @property
    def text(self) -> str:
        return _normalize_text(" ".join(c for c in self.cells if c).strip())


def _cluster_words(words: Sequence[dict[str, Any]], gap: float = 18.0) -> list[str]:
    if not words:
        return []
    ordered = sorted(words, key=lambda w: w["x0"])
    cols: list[list[dict[str, Any]]] = []
    for w in ordered:
        if not cols or w["x0"] - cols[-1][-1]["x1"] > gap:
            cols.append([w])
        else:
            cols[-1].append(w)
    return ["".join(x["text"] for x in col).strip() for col in cols if any(x["text"].strip() for x in col)]


def extract_page_lines(page: Any, *, y_tolerance: float = 3.0, col_gap: float = 18.0) -> list[PdfLine]:
    words = page.extract_words(x_tolerance=2, y_tolerance=y_tolerance) or []
    buckets: dict[float, list[dict[str, Any]]] = {}
    for w in words:
        y = round(w["top"] / y_tolerance) * y_tolerance
        buckets.setdefault(y, []).append(w)
    lines: list[PdfLine] = []
    for y in sorted(buckets.keys()):
        cells = _cluster_words(buckets[y], gap=col_gap)
        if cells:
            lines.append(PdfLine(y=y, cells=cells))
    return lines


def _is_table_header(cells: list[str]) -> str | None:
    norm = [_normalize_text(c) for c in cells]
    joined = " ".join(norm)
    if "指标名称" in joined and ("本期" in joined or "2025" in joined):
        return "metrics5" if ("业务动因" in joined or "同比" in joined) else "metrics3"
    if "产品名称" in joined and "产品类型" in joined:
        return "product4"
    if norm and norm[0] == "地区" and "占比" in joined:
        return "region4"
    if norm and norm[0] == "行业" and "占比" in joined:
        return "industry4"
    if "运营模式" in joined and "业务特点" in joined:
        return "ops3"
    return None


def _md_escape_cell(val: str) -> str:
    return val.replace("|", "\\|").replace("\n", " ").strip()


def _table_to_md(headers: list[str], rows: list[list[str]]) -> str:
    hdr = [_md_escape_cell(h) for h in headers]
    out = ["| " + " | ".join(hdr) + " |", "| " + " | ".join(["---"] * len(hdr)) + " |"]
    for row in rows:
        padded = row + [""] * (len(hdr) - len(row))
        out.append("| " + " | ".join(_md_escape_cell(c) for c in padded[: len(hdr)]) + " |")
    return "\n".join(out)


def _is_amount_cell(text: str) -> bool:
    t = text.strip()
    if not t:
        return False
    if NUMERIC_CELL_RE.match(t):
        return True
    return bool(re.search(r"\d", t)) and ("亿" in t or "元" in t or "%" in t)


def _extract_amount_triple(cells: list[str]) -> tuple[str, str, str] | None:
    """从一行取出 本期/上期/同比 三列。"""
    if len(cells) >= 4 and _is_amount_cell(cells[1]):
        return cells[1], cells[2], cells[3]
    if len(cells) >= 3 and all(_is_amount_cell(c) for c in cells[:3]):
        return cells[0], cells[1], cells[2]
    return None


def _is_data_amount_line(cells: list[str]) -> bool:
    return _extract_amount_triple(cells) is not None


def _collect_table_lines(lines: list[PdfLine], start: int) -> tuple[list[PdfLine], int]:
    chunk: list[PdfLine] = []
    i = start + 1
    while i < len(lines):
        text = lines[i].text
        if not text:
            i += 1
            continue
        if text.startswith("洞察") or text.startswith("结论") or SECTION_START_RE.match(text):
            break
        if i > start + 1 and _is_table_header(lines[i].cells):
            break
        if text.startswith("主营业务变化分析"):
            break
        chunk.append(lines[i])
        i += 1
    return chunk, i


def _parse_metrics5_table(lines: list[PdfLine], start: int) -> tuple[str, int]:
    headers = ["指标名称", "本期(2025)", "上期(2024)", "同比变化", "业务动因"]
    table_lines, next_i = _collect_table_lines(lines, start)
    rows: list[list[str]] = []
    used: set[int] = set()

    for j, line in enumerate(table_lines):
        if j in used:
            continue
        triple = _extract_amount_triple(line.cells)
        if not triple:
            continue

        metric = ""
        reason_parts: list[str] = []
        if len(line.cells) >= 4 and not _is_amount_cell(line.cells[0]):
            metric = line.cells[0]

        if j > 0 and j - 1 not in used:
            prev = table_lines[j - 1]
            if len(prev.cells) == 1:
                reason_parts.append(prev.cells[0])
                used.add(j - 1)
            elif len(prev.cells) >= 2 and not _is_data_amount_line(prev.cells):
                metric = (prev.cells[0] + " " + metric).strip()
                reason_parts.extend(prev.cells[1:])
                used.add(j - 1)

        if j + 1 < len(table_lines) and j + 1 not in used:
            nxt = table_lines[j + 1]
            if len(nxt.cells) == 1:
                reason_parts.append(nxt.cells[0])
                used.add(j + 1)
            elif len(nxt.cells) >= 2 and not _is_data_amount_line(nxt.cells):
                metric = (metric + " " + nxt.cells[0]).strip()
                reason_parts.extend(nxt.cells[1:])
                used.add(j + 1)

        rows.append([metric, *triple, " ".join(x for x in reason_parts if x).strip()])
        used.add(j)

    def _tight_cn(s: str) -> str:
        return re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", s.strip())

    rows = [[_tight_cn(c) if i in (0, 4) else c.strip() for i, c in enumerate(r)] for r in rows]
    return _table_to_md(headers, rows), next_i


def _parse_product4_table(lines: list[PdfLine], start: int) -> tuple[str, int]:
    headers = ["产品名称", "产品类型", "市场表现", "生命周期阶段"]
    table_lines, next_i = _collect_table_lines(lines, start)
    rows: list[list[str]] = []

    def _tight_cn(s: str) -> str:
        return re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", s.strip())

    product_idx = [i for i, ln in enumerate(table_lines) if _is_product_row(ln.cells)]
    next_prefix: list[str] = []
    for j in range(0, product_idx[0] if product_idx else 0):
        if len(table_lines[j].cells) == 1:
            next_prefix.append(_normalize_text(table_lines[j].cells[0]))

    for k, pi in enumerate(product_idx):
        cells = [_normalize_text(c) for c in table_lines[pi].cells]
        name = cells[0]
        ptype = cells[1] if len(cells) > 1 else ""
        market_parts = list(next_prefix)
        next_prefix = []
        stage_parts: list[str] = []

        if len(cells) == 3 and _is_lifecycle_fragment(cells[2]):
            stage_parts.append(cells[2])
        elif len(cells) >= 4:
            market_parts.append(cells[2])
            stage_parts.append(cells[3])
        elif len(cells) >= 3:
            market_parts.append(cells[2])

        suffix_end = product_idx[k + 1] if k + 1 < len(product_idx) else len(table_lines)
        singles: list[str] = []
        for j in range(pi + 1, suffix_end):
            if len(table_lines[j].cells) == 1:
                singles.append(_normalize_text(table_lines[j].cells[0]))
        lc = [f for f in singles if _is_lifecycle_fragment(f)]
        non_lc = [f for f in singles if not _is_lifecycle_fragment(f)]
        stage_parts.extend(lc)
        if k + 1 < len(product_idx):
            if non_lc:
                market_parts.extend(non_lc[:-1])
                next_prefix = [non_lc[-1]]
        else:
            market_parts.extend(non_lc)

        rows.append(
            [
                _tight_cn(name),
                _tight_cn(ptype),
                _tight_cn(" ".join(x for x in market_parts if x)),
                _tight_cn(" ".join(x for x in stage_parts if x)),
            ]
        )

    return _table_to_md(headers, rows), next_i


def _parse_region4_table(lines: list[PdfLine], start: int) -> tuple[str, int]:
    headers = ["地区", "营业收入（亿元）", "占比", "代表产品及策略"]
    table_lines, next_i = _collect_table_lines(lines, start)
    rows: list[list[str]] = []
    pending_col4 = ""
    i = 0
    while i < len(table_lines):
        cells = [_normalize_text(c) for c in table_lines[i].cells]
        if cells and cells[0] in ("境内", "境外"):
            col4 = pending_col4
            pending_col4 = ""
            if len(cells) > 3:
                col4 = (col4 + " " + cells[3]).strip()
            row = [cells[0], cells[1] if len(cells) > 1 else "", cells[2] if len(cells) > 2 else "", col4]
            i += 1
            while i < len(table_lines):
                nxt = table_lines[i].cells
                if len(nxt) == 1:
                    row[3] = (row[3] + " " + _normalize_text(nxt[0])).strip()
                    i += 1
                    continue
                if _normalize_text(nxt[0]) in ("境内", "境外"):
                    break
                if len(nxt) >= 3 and _normalize_text(nxt[0]) not in ("境内", "境外"):
                    pending_col4 = (pending_col4 + " " + " ".join(_normalize_text(c) for c in nxt)).strip()
                    i += 1
                    continue
                break
            rows.append(row)
            continue
        if len(cells) >= 1 and cells[0] not in ("境内", "境外"):
            pending_col4 = (pending_col4 + " " + " ".join(cells)).strip()
        i += 1
    return _table_to_md(headers, rows), next_i


def _parse_industry4_table(lines: list[PdfLine], start: int) -> tuple[str, int]:
    headers = ["行业", "营业收入（亿元）", "占比", "业务动态"]
    table_lines, next_i = _collect_table_lines(lines, start)
    rows: list[list[str]] = []
    pending = ""
    for line in table_lines:
        cells = [_normalize_text(c) for c in line.cells]
        if cells and cells[0] == "传媒":
            col4 = (pending + " " + " ".join(cells[3:])).strip() if len(cells) > 3 else pending
            rows.append([cells[0], cells[1] if len(cells) > 1 else "", cells[2] if len(cells) > 2 else "", col4])
            pending = ""
            continue
        if len(cells) == 1:
            if rows:
                rows[-1][3] = (rows[-1][3] + " " + cells[0]).strip()
            else:
                pending = (pending + " " + cells[0]).strip()
        elif not rows:
            pending = (pending + " " + " ".join(cells)).strip()
        elif len(cells) == 1 and rows:
            rows[-1][3] = (rows[-1][3] + " " + cells[0]).strip()
    return _table_to_md(headers, rows), next_i


def _parse_ops3_table(lines: list[PdfLine], start: int) -> tuple[str, int]:
    headers = ["运营模式", "业务特点", "代表案例"]
    table_lines, next_i = _collect_table_lines(lines, start)
    rows: list[list[str]] = []
    i = 0
    while i < len(table_lines):
        cells = table_lines[i].cells
        if cells and cells[0] in ("自主运营", "第三方联合运营"):
            row = [cells[0], cells[1] if len(cells) > 1 else "", " ".join(cells[2:])]
            i += 1
            while i < len(table_lines) and len(table_lines[i].cells) == 1:
                frag = table_lines[i].cells[0]
                if "《" in frag:
                    row[2] = (row[2] + " " + frag).strip()
                else:
                    row[1] = (row[1] + " " + frag).strip()
                i += 1
            rows.append(row)
            continue
        i += 1
    return _table_to_md(headers, rows), next_i


def _parse_metrics3_table(lines: list[PdfLine], start: int) -> tuple[str, int]:
    hdr = lines[start].cells
    headers = hdr if len(hdr) >= 3 else ["指标名称", "2025年数据", "同比变化"]
    table_lines, next_i = _collect_table_lines(lines, start)
    rows: list[list[str]] = []
    for line in table_lines:
        cells = line.cells
        if len(cells) >= 2:
            rows.append((cells + ["", ""])[: len(headers)])
        elif len(cells) == 1 and rows:
            rows[-1][-1] = (rows[-1][-1] + " " + cells[0]).strip()
    return _table_to_md(headers, rows), next_i


TABLE_PARSERS = {
    "metrics5": _parse_metrics5_table,
    "product4": _parse_product4_table,
    "region4": _parse_region4_table,
    "industry4": _parse_industry4_table,
    "ops3": _parse_ops3_table,
    "metrics3": _parse_metrics3_table,
}


def _preprocess_prose_line(line: str) -> list[str]:
    """拆出章节标题、列表项，便于段落 reflow。"""
    t = _normalize_text(line.strip())
    if not t:
        return [""]
    t = re.sub(r"\s*([一二三四五六七八九十]+[、．.])\s*", r"\n\1", t)
    t = re.sub(r"(亮点总结|风险总结|洞察：|结论：)", r"\n\1\n", t)
    t = re.sub(r"(?<=[^\d])\s+(\d{1,2}\.(?!\d))", r"\n\1", t)
    t = re.sub(r"(?<=[^·])\s+(·)", r"\n\1", t)
    parts: list[str] = []
    for piece in t.split("\n"):
        p = piece.strip()
        if not p:
            parts.append("")
            continue
        m = re.match(r"^([一二三四五六七八九十]+[、．.][^ \n]{1,20})\s+(.+)$", p)
        if m:
            parts.extend([m.group(1).strip(), m.group(2).strip()])
            continue
        m2 = re.match(r"^(主营业务变化分析[^ \n]{0,24})\s+(.+)$", p)
        if m2:
            parts.extend([m2.group(1).strip(), m2.group(2).strip()])
        else:
            parts.append(p)
    return parts if parts else [""]


def _should_merge_lines(prev: str, nxt: str) -> bool:
    if not prev or not nxt:
        return False
    if re.match(r"^\d+\.$", nxt.strip()):
        return False
    if SECTION_START_RE.match(nxt) or BULLET_RE.match(nxt):
        return False
    if nxt.startswith("主营业务") or nxt.startswith("表"):
        return False
    if LIST_ITEM_RE.match(prev):
        return not LIST_ITEM_RE.match(nxt)
    if LIST_ITEM_RE.match(nxt):
        return False
    if prev.endswith(("。", "！", "？", "；", "：", ")", "）", "%", "】", "”", "’")):
        return False
    return True


def _reflow_prose_lines(raw_lines: list[str]) -> list[str]:
    expanded: list[str] = []
    for line in raw_lines:
        expanded.extend(_preprocess_prose_line(line))

    out: list[str] = []
    buf = ""

    def flush() -> None:
        nonlocal buf
        if buf.strip():
            out.append(buf.strip())
        buf = ""

    for line in expanded:
        if not line:
            if buf and not buf.rstrip().endswith(("。", "！", "？", "；", "：", "%", ")", "）", "”", "’")):
                continue
            flush()
            continue
        if re.match(r"^\d+\.$", line.strip()):
            continue
        if re.match(r"^(\d+\.)\s*$", line.strip()):
            continue
        if LIST_ITEM_RE.match(line):
            flush()
            buf = line.strip()
            continue
        if BULLET_RE.match(line) or SECTION_START_RE.match(line):
            flush()
            if re.match(r"^[一二三四五六七八九十百]+[、．.]$", line.strip()):
                buf = line.strip()
            else:
                out.append(line.strip())
            continue
        if buf and re.match(r"^[一二三四五六七八九十百]+[、．.]$", buf):
            buf = f"{buf}{line.strip()}"
            continue
        if buf and _should_merge_lines(buf, line):
            buf = f"{buf} {line.strip()}"
        else:
            flush()
            buf = line.strip()
    flush()
    return [_tight_cn_prose(x) for x in out]


def _tight_cn_prose(line: str) -> str:
    if line.startswith("|"):
        return line
    return re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", line.strip())


def _lines_to_markdown(lines: list[PdfLine]) -> str:
    blocks: list[str] = []
    prose_buf: list[str] = []
    i = 0

    def flush_prose() -> None:
        nonlocal prose_buf
        if not prose_buf:
            return
        for para in _reflow_prose_lines(prose_buf):
            if MAIN_SECTION_HEADING_RE.match(para):
                blocks.append(f"### {para}")
            else:
                blocks.append(para)
            blocks.append("")
        prose_buf = []

    while i < len(lines):
        kind = _is_table_header(lines[i].cells)
        if kind and kind in TABLE_PARSERS:
            flush_prose()
            table_md, next_i = TABLE_PARSERS[kind](lines, i)
            if table_md.strip():
                blocks.append(table_md)
                blocks.append("")
            i = next_i
            continue
        prose_buf.append(lines[i].text)
        i += 1

    flush_prose()
    while blocks and blocks[-1] == "":
        blocks.pop()
    return "\n".join(blocks)


def convert_vertical_pdf_to_markdown(pdf_path: str) -> str:
    """单家公司纵向分析 PDF → Markdown 正文（不含 ## 标题行）。"""
    all_lines: list[PdfLine] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_lines = extract_page_lines(page)
            if page_lines:
                all_lines.extend(page_lines)
    if not all_lines:
        return ""
    return _lines_to_markdown(all_lines).strip() + "\n"


def replace_company_section_in_md(
    md_text: str,
    company_index: int,
    company_name: str,
    new_body: str,
) -> str:
    """替换 ## N. 公司名 章节正文。"""
    pattern = re.compile(rf"^##\s+{company_index}\.\s+{re.escape(company_name)}\s*$", re.MULTILINE)
    m = pattern.search(md_text)
    if not m:
        raise ValueError(f"未找到章节 ## {company_index}. {company_name}")
    start = m.end()
    next_sec = re.search(rf"^##\s+{company_index + 1}\.\s+", md_text[start:], re.MULTILINE)
    end = start + next_sec.start() if next_sec else len(md_text)
    body = new_body.strip("\n") + "\n\n"
    return md_text[:start] + "\n\n" + body + md_text[end:].lstrip("\n")
