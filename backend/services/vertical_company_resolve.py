"""纵向 PDF 文件名 → canonical company id / 展示名。

公开仓库仅含 canonical 代号规则（wm/37…）。内网中文 PDF 文件名通过运行时配置加载：
- `{upload_dir}/competitor/vertical_company_rules.json`（推荐，持久化在 uploads 卷）
- 环境变量 `VERTICAL_COMPANY_RULES_JSON`（生产 .env，勿提交 Git）
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from backend.config import settings
from backend.services.competitor_report_store import competitor_dir
from backend.services.vertical_report_parser import CANONICAL_PEER_IDS

RULES_FILENAME = "vertical_company_rules.json"

# 文件名含 canonical id（如 wm、37）或英文别名
_BUILTIN_RULES: list[tuple[str, re.Pattern[str]]] = [
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


def reset_filename_rules_cache() -> None:
    """测试或热更新 rules 文件后清缓存。"""
    _merged_filename_rules.cache_clear()


def _rules_from_json_payload(payload: object) -> list[tuple[str, re.Pattern[str]]]:
    if not isinstance(payload, list):
        return []
    out: list[tuple[str, re.Pattern[str]]] = []
    seen: set[tuple[str, str]] = set()
    for item in payload:
        if not isinstance(item, dict):
            continue
        cid = str(item.get("id") or "").strip()
        if cid not in CANONICAL_PEER_IDS:
            continue
        patterns = item.get("patterns")
        if not isinstance(patterns, list):
            continue
        for raw in patterns:
            pat = str(raw or "").strip()
            if not pat:
                continue
            key = (cid, pat)
            if key in seen:
                continue
            seen.add(key)
            out.append((cid, re.compile(re.escape(pat), re.I)))
    return out


def _load_runtime_rules() -> list[tuple[str, re.Pattern[str]]]:
    out: list[tuple[str, re.Pattern[str]]] = []
    env_raw = (settings.vertical_company_rules_json or "").strip()
    if env_raw:
        try:
            out.extend(_rules_from_json_payload(json.loads(env_raw)))
        except json.JSONDecodeError:
            pass
    path = competitor_dir() / RULES_FILENAME
    if path.is_file():
        try:
            out.extend(_rules_from_json_payload(json.loads(path.read_text(encoding="utf-8"))))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            pass
    return out


@lru_cache(maxsize=1)
def _merged_filename_rules() -> tuple[tuple[str, re.Pattern[str]], ...]:
    return tuple(_load_runtime_rules() + _BUILTIN_RULES)


def resolve_company_id_from_filename(filename: str) -> str | None:
    stem = Path(filename).stem
    low = stem.lower()
    if low in CANONICAL_PEER_IDS:
        return low
    if low.startswith("v-"):
        cid = low[2:]
        if cid in CANONICAL_PEER_IDS:
            return cid
    for cid, pat in _merged_filename_rules():
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
