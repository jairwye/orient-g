"""各公司纵向分析报告 MD → 结构化 JSON（按公司 + 内部 ### 分节）。"""
from __future__ import annotations

import re
from typing import Any

from backend.services.competitor_report_parser import _parse_chunk

PARSER_VERSION = "1.1.0"

COMPANY_SECTION_RE = re.compile(r"^##\s+\d+\.\s+(.+?)\s*$", re.MULTILINE)
INTERNAL_SECTION_RE = re.compile(r"^###\s+(.+?)\s*$", re.MULTILINE)

# 纵向蓝本按章节顺序映射到与行业汇析一致的 canonical peer id（不含真实公司名）
CANONICAL_PEER_IDS = ("37", "wm", "zq", "tr", "hq", "xs", "la")


def _resolve_company_id(index: int) -> str:
    if index < len(CANONICAL_PEER_IDS):
        return CANONICAL_PEER_IDS[index]
    return f"peer-{index + 1}"


def _section_index(title: str, fallback: int) -> str:
    m = re.match(r"^([一二三四五六七八九十百]+)[、．.]", title.strip())
    if not m:
        return f"{fallback:02d}"
    return f"{_cn_numeral_to_int(m.group(1)) or fallback:02d}"


def _cn_numeral_to_int(text: str) -> int | None:
    if not text:
        return None
    digit = {"零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    if text == "十":
        return 10
    if text.startswith("十"):
        tail = text[1:]
        return 10 + (digit.get(tail, 0) if tail else 0)
    if "十" in text:
        left, _, right = text.partition("十")
        tens = digit.get(left, 1) if left else 1
        ones = digit.get(right, 0) if right else 0
        return tens * 10 + ones
    if len(text) == 1 and text in digit:
        return digit[text]
    return None


def _parse_company_body(body: str, snap_id: str, warnings: list[str]) -> list[dict[str, Any]]:
    matches = list(INTERNAL_SECTION_RE.finditer(body))
    if not matches:
        blocks = _parse_chunk(body.strip(), snap_id, warnings)
        if not blocks:
            return []
        return [{"id": f"{snap_id}-01", "title": "正文", "blocks": blocks}]

    sections: list[dict[str, Any]] = []
    seen_ids: dict[str, int] = {}
    for i, m in enumerate(matches):
        title = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        chunk = body[start:end].strip()
        idx = _section_index(title, i + 1)
        base_id = f"{snap_id}-{idx}"
        n = seen_ids.get(base_id, 0) + 1
        seen_ids[base_id] = n
        sec_id = base_id if n == 1 else f"{base_id}-{n}"
        sections.append(
            {
                "id": sec_id,
                "title": title,
                "blocks": _parse_chunk(chunk, sec_id, warnings),
            }
        )
    return sections


def parse_vertical_report(md_text: str) -> dict[str, Any]:
    warnings: list[str] = []
    matches = list(COMPANY_SECTION_RE.finditer(md_text))
    if not matches:
        raise ValueError("未找到公司章节（## 1. 公司名）")

    intro_raw = md_text[: matches[0].start()].strip()
    intro_blocks: list[dict[str, Any]] = []
    if intro_raw:
        intro_blocks = _parse_chunk(intro_raw, "v-intro", warnings)

    title = "各公司纵向对比"
    for line in intro_raw.splitlines():
        s = line.strip()
        if s.startswith("# ") and not s.startswith("##"):
            title = s.lstrip("# ").strip()
            break

    companies: list[dict[str, Any]] = []
    for i, m in enumerate(matches):
        name = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(md_text)
        body = md_text[start:end]
        cid = _resolve_company_id(i)
        if i >= len(CANONICAL_PEER_IDS):
            warnings.append(f"超出标准 peer 数量，使用 {cid}")
        snap_id = f"v-{cid}"
        sections = _parse_company_body(body, snap_id, warnings)
        flat_blocks: list[dict[str, Any]] = []
        for sec in sections:
            flat_blocks.extend(sec["blocks"])
        companies.append(
            {
                "id": cid,
                "snap_id": snap_id,
                "name": name,
                "sections": sections,
                "blocks": flat_blocks,
            }
        )

    return {
        "version": 1,
        "meta": {
            "title": title,
            "parser_version": PARSER_VERSION,
            "company_count": len(companies),
        },
        "intro": intro_blocks,
        "companies": companies,
        "warnings": warnings,
    }
