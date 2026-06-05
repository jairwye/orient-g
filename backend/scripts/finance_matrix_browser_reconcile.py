#!/usr/bin/env python3
"""按 subject+mode 去重，保留最新一行并重新验收。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "backend" / "tests" / "reports" / "finance_matrix_browser_report.json"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from finance_matrix_browser_validate import validate_row  # noqa: E402


def _key(r: dict) -> str:
    return f"{r.get('category')}::{r.get('subject')}::{r.get('mode')}"


def main() -> None:
    rows = json.loads(REPORT.read_text(encoding="utf-8"))
    latest: dict[str, dict] = {}
    for r in rows:
        if not isinstance(r, dict) or not r.get("subject"):
            continue
        latest[_key(r)] = validate_row(dict(r))
    out = list(latest.values())
    # 稳定排序：按 MATRIX 顺序
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from finance_matrix_cases import MATRIX  # noqa: E402

    order = {f"{c}::{s}::{m}": i for i, (c, s, m, _) in enumerate(MATRIX)}
    out.sort(key=lambda r: order.get(_key(r), 999))
    REPORT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ok_n = sum(1 for r in out if r.get("ok"))
    print(json.dumps({"rows": len(out), "ok_pass": ok_n, "ok_false": len(out) - ok_n}, ensure_ascii=False))


if __name__ == "__main__":
    main()
