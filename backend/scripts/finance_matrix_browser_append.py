#!/usr/bin/env python3
"""Append one Chrome DevTools matrix row to finance_matrix_browser_report.json."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "backend" / "tests" / "reports" / "finance_matrix_browser_report.json"
_SCRIPTS = Path(__file__).resolve().parent
import sys

sys.path.insert(0, str(_SCRIPTS))
from finance_matrix_browser_validate import validate_row  # noqa: E402


def main() -> None:
    if len(sys.argv) > 1 and Path(sys.argv[1]).is_file():
        raw = Path(sys.argv[1]).read_bytes().decode("utf-8")
    else:
        raw = sys.stdin.buffer.read().decode("utf-8")
    row = json.loads(raw)
    row.setdefault("at", datetime.now(timezone.utc).isoformat(timespec="seconds"))
    row.setdefault("account", "finance_test")
    row.setdefault("folder", "竞品财报25")
    row.setdefault("tool", "chrome-devtools-mcp")
    row = validate_row(row)
    data: list = []
    if REPORT.is_file():
        data = json.loads(REPORT.read_text(encoding="utf-8"))
    data.append(row)
    # 同 key 只保留最新一行
    latest: dict[str, dict] = {}
    for r in data:
        if isinstance(r, dict) and r.get("subject"):
            k = f"{r.get('category')}::{r.get('subject')}::{r.get('mode')}"
            latest[k] = r
    from finance_matrix_cases import MATRIX  # noqa: E402

    order = {f"{c}::{s}::{m}": i for i, (c, s, m, _) in enumerate(MATRIX)}
    cleaned = sorted(latest.values(), key=lambda r: order.get(f"{r.get('category')}::{r.get('subject')}::{r.get('mode')}", 999))
    REPORT.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": row["ok"], "subject": row.get("subject"), "mode": row.get("mode")}))


if __name__ == "__main__":
    main()
