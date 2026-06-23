"""纵向 PDF 文件名 → canonical company id / 展示名（Git 侧仅用代号；展示名来自运行时文件名 stem）。"""
from __future__ import annotations

import re
from pathlib import Path

from backend.services.vertical_report_parser import CANONICAL_PEER_IDS

# 文件名须含 canonical id（如 wm、37）或英文别名；内网中文 PDF 名由 stem 解析展示名
_FILENAME_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("37", re.compile(r"(?:^|[_.-])37(?:[_.-]|$|\d)|\b37\b|sanqi|3.?7", re.I)),
    ("wm", re.compile(r"(?:^|[_.-])wm(?:[_.-]|$|\d)|\bwm\b|perfect\s*world", re.I)),
    ("zq", re.compile(r"(?:^|[_.-])zq(?:[_.-]|$|\d)|\bzq\b|zhangqu", re.I)),
    ("tr", re.compile(r"(?:^|[_.-])tr(?:[_.-]|$|\d)|\btr\b|taren", re.I)),
    ("hq", re.compile(r"(?:^|[_.-])hq(?:[_.-]|$|\d)|\bhq\b|huaqing", re.I)),
    ("xs", re.compile(r"(?:^|[_.-])xs(?:[_.-]|$|\d)|\bxs\b|pixel", re.I)),
    ("la", re.compile(r"(?:^|[_.-])la(?:[_.-]|$|\d)|\bla\b|lvan", re.I)),
]

_STEM_CLEAN = re.compile(
    r"20\d{2}.*?(?:年度|年)?(?:报告|分析|解读|纵向)?|[_\-]\d+$|\.pdf$",
    re.I,
)


def resolve_company_id_from_filename(filename: str) -> str | None:
    stem = Path(filename).stem
    low = stem.lower()
    if low in CANONICAL_PEER_IDS:
        return low
    if low.startswith("v-"):
        cid = low[2:]
        if cid in CANONICAL_PEER_IDS:
            return cid
    for cid, pat in _FILENAME_RULES:
        if pat.search(stem):
            return cid
    return None


def display_name_for_company(company_id: str, filename: str) -> str:
    stem = Path(filename).stem
    name = _STEM_CLEAN.sub("", stem).strip(" _-")
    if name and name.lower() not in CANONICAL_PEER_IDS:
        return name
    return company_id


def order_pdf_entries(entries: list[tuple[str, Path]]) -> list[tuple[str, Path, str]]:
    """[(filename, path)] → [(company_id, path, display_name)]；未识别 id 的跳过。"""
    resolved: list[tuple[str, Path, str, int]] = []
    for fname, path in entries:
        cid = resolve_company_id_from_filename(fname)
        if not cid:
            continue
        idx = CANONICAL_PEER_IDS.index(cid) if cid in CANONICAL_PEER_IDS else 99
        resolved.append((cid, path, display_name_for_company(cid, fname), idx))
    resolved.sort(key=lambda x: (x[3], x[0]))
    return [(cid, path, name) for cid, path, name, _ in resolved]
