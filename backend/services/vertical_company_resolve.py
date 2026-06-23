"""纵向 PDF 文件名 → canonical company id / 展示名。

公开仓库默认仅含 canonical 代号规则（wm/37…）。内网中文 PDF 名可通过：
1. `{upload_dir}/competitor/vertical_company_rules.json`（uploads 卷，推荐覆盖）
2. 环境变量 `VERTICAL_COMPANY_RULES_JSON`
3. 生产部署且未显式配置 1/2 时，启用内建中文规则（`VERTICAL_BUILTIN_FILENAME_RULES=false` 可关）
"""
from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path

from backend.config import settings
from backend.services.competitor_report_store import competitor_dir
from backend.services.vertical_report_parser import CANONICAL_PEER_IDS

logger = logging.getLogger(__name__)

RULES_FILENAME = "vertical_company_rules.json"

_BUILTIN_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("37", re.compile(r"(?:^|[_.-])37(?:[_.-]|$|\d)|\b37\b|sanqi|3.?7", re.I)),
    ("wm", re.compile(r"(?:^|[_.-])wm(?:[_.-]|$|\d)|\bwm\b|perfect\s*world", re.I)),
    ("zq", re.compile(r"(?:^|[_.-])zq(?:[_.-]|$|\d)|\bzq\b|zhangqu", re.I)),
    ("tr", re.compile(r"(?:^|[_.-])tr(?:[_.-]|$|\d)|\btr\b|taren", re.I)),
    ("hq", re.compile(r"(?:^|[_.-])hq(?:[_.-]|$|\d)|\bhq\b|huaqing", re.I)),
    ("xs", re.compile(r"(?:^|[_.-])xs(?:[_.-]|$|\d)|\bxs\b|pixel", re.I)),
    ("la", re.compile(r"(?:^|[_.-])la(?:[_.-]|$|\d)|\bla\b|lvan", re.I)),
]

# 内网生产默认 7 家 PDF 文件名关键词（仅在内建回退启用时加载；公开 fork 请设 VERTICAL_BUILTIN_FILENAME_RULES=false）
_BUILTIN_CN_PATTERNS: list[tuple[str, list[str]]] = [
    ("37", ["三七", "37互娱"]),
    ("wm", ["完美世界", "完美"]),
    ("zq", ["掌趣"]),
    ("tr", ["塔人"]),
    ("hq", ["华清飞扬", "华清"]),
    ("xs", ["像素软件", "像素"]),
    ("la", ["绿岸"]),
]

_STEM_CLEAN = re.compile(
    r"20\d{2}.*?(?:年度|年)?(?:报告|分析|解读|纵向)?|[_\-]\d+$|\.pdf$",
    re.I,
)


def reset_filename_rules_cache() -> None:
    _merged_filename_rules.cache_clear()


def rules_config_path() -> Path:
    return competitor_dir() / RULES_FILENAME


def has_explicit_runtime_rules_config() -> bool:
    if (settings.vertical_company_rules_json or "").strip():
        return True
    return rules_config_path().is_file()


def _should_use_builtin_cn_rules() -> bool:
    if settings.vertical_builtin_filename_rules is False:
        return False
    if has_explicit_runtime_rules_config():
        return False
    if settings.vertical_builtin_filename_rules is True:
        return True
    if settings.app_env == "production":
        return True
    # compose 生产常设 COMPETITOR_FIXTURE_FALLBACK=false 但未设 APP_ENV 时仍启用
    return not settings.effective_competitor_fixture_fallback


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


def _builtin_cn_rules() -> list[tuple[str, re.Pattern[str]]]:
    if not _should_use_builtin_cn_rules():
        return []
    out: list[tuple[str, re.Pattern[str]]] = []
    for cid, patterns in _BUILTIN_CN_PATTERNS:
        for p in patterns:
            out.append((cid, re.compile(re.escape(p), re.I)))
    return out


def _load_runtime_rules() -> list[tuple[str, re.Pattern[str]]]:
    out: list[tuple[str, re.Pattern[str]]] = []
    env_raw = (settings.vertical_company_rules_json or "").strip()
    if env_raw:
        try:
            out.extend(_rules_from_json_payload(json.loads(env_raw)))
        except json.JSONDecodeError:
            logger.warning("VERTICAL_COMPANY_RULES_JSON 不是合法 JSON，已忽略")
    path = rules_config_path()
    if path.is_file():
        try:
            out.extend(_rules_from_json_payload(json.loads(path.read_text(encoding="utf-8"))))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
            logger.warning("读取 %s 失败: %s", path, exc)
    return out


@lru_cache(maxsize=1)
def _merged_filename_rules() -> tuple[tuple[str, re.Pattern[str]], ...]:
    runtime = _load_runtime_rules()
    builtin_cn = _builtin_cn_rules()
    merged = tuple(runtime + builtin_cn + _BUILTIN_RULES)
    if builtin_cn:
        logger.info(
            "vertical PDF 文件名：使用内建中文规则 %d 条（upload_dir=%s）",
            len(builtin_cn),
            settings.upload_dir,
        )
    elif runtime:
        logger.info("vertical PDF 文件名：已加载自定义规则 %d 条", len(runtime))
    return merged


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
    resolved: list[tuple[str, Path, str, int]] = []
    for fname, path in entries:
        cid = resolve_company_id_from_filename(fname)
        if not cid:
            continue
        idx = CANONICAL_PEER_IDS.index(cid) if cid in CANONICAL_PEER_IDS else 99
        resolved.append((cid, path, display_name_for_company(cid, fname), idx))
    resolved.sort(key=lambda x: (x[3], x[0]))
    return [(cid, path, name) for cid, path, name, _ in resolved]
