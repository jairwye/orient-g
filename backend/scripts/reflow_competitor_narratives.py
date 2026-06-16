#!/usr/bin/env python3
"""将蓝本 MD 中长叙事按公司名/主题小标题拆成多段（空行分隔），便于页面 plain 叙事分行展示。"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MD = REPO_ROOT / "uploads" / "行业财报汇析-2025年_数据文档_YYCQ版.md"

COMPANIES = (
    "游艺春秋",
    "三七互娱",
    "完美世界",
    "掌趣科技",
    "塔人网络",
    "华清飞扬",
    "像素软件",
    "绿岸网络",
)
COMPANY_RE = "|".join(re.escape(c) for c in COMPANIES)


def _split_by_company(text: str) -> list[str]:
    """在句号/分号后、公司名出现处拆段。"""
    text = text.strip()
    if not text:
        return []
    pattern = re.compile(rf"(?<=[。；])\s*(?=(?:{COMPANY_RE}))")
    parts = [p.strip() for p in pattern.split(text) if p.strip()]
    return parts if len(parts) >= 2 else [text]


def _reflow_bold_paragraph(line: str) -> str:
    m = re.match(r"^(\*\*[^*]+\*\*)([\s\S]*)$", line.strip())
    if not m:
        return line
    prefix, body = m.group(1), m.group(2).strip()
    if not body:
        return prefix
    # 主题小标题块（sec-06-4 等）且正文较短：不拆
    if len(body) < 120 and body.count("。") <= 1:
        return f"{prefix} {body}".strip()
    chunks = _split_by_company(body)
    if len(chunks) <= 1:
        return f"{prefix} {body}".strip()
    return prefix + "\n\n" + "\n\n".join(chunks)


def _reflow_plain_paragraph(line: str) -> str:
    s = line.strip()
    if not s or s.startswith("|") or s.startswith("#") or s.startswith(">"):
        return line
    if s.startswith("**"):
        return _reflow_bold_paragraph(s)
    if re.search(r"\(\d+\)", s) or "：" in s[:20]:
        return line
    if len(s) < 100:
        return line
    chunks = _split_by_company(s)
    if len(chunks) <= 1:
        return line
    return "\n\n".join(chunks)


def reflow_markdown(text: str) -> tuple[str, int]:
    lines = text.splitlines()
    out: list[str] = []
    changed = 0
    for line in lines:
        new_line = _reflow_plain_paragraph(line)
        if new_line != line:
            changed += 1
            out.extend(new_line.splitlines())
        else:
            out.append(line)
    return "\n".join(out) + ("\n" if text.endswith("\n") else ""), changed


def main() -> int:
    md_path = DEFAULT_MD
    text = md_path.read_text(encoding="utf-8")
    new_text, n = reflow_markdown(text)
    if n == 0:
        print("No narrative lines reflowed.")
        return 0
    md_path.write_text(new_text, encoding="utf-8")
    print(f"Reflowed {n} narrative block(s) in {md_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
