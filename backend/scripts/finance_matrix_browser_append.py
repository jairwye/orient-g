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


def append_matrix_row(
    row: dict,
    *,
    report_path: Path | None = None,
    matrix: list[tuple[str, str, str, str]] | None = None,
) -> dict:
    """validate + 写入 report（同 key 保留最新）；供 CDP runner 进程内调用，避免子进程编码问题。"""
    _root = Path(__file__).resolve().parents[2]
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))
    from finance_matrix_cases import MATRIX as DEFAULT_MATRIX  # noqa: E402

    use_report = report_path or REPORT
    use_matrix = matrix or DEFAULT_MATRIX

    row = dict(row)
    row.setdefault("at", datetime.now(timezone.utc).isoformat(timespec="seconds"))
    row.setdefault("account", "finance_test")
    row.setdefault("folder", "竞品财报25")
    row.setdefault("tool", "chrome-devtools-mcp")
    row = validate_row(row)
    data: list = []
    if use_report.is_file():
        data = json.loads(use_report.read_text(encoding="utf-8"))
    data.append(row)
    latest: dict[str, dict] = {}
    for r in data:
        if isinstance(r, dict) and r.get("subject"):
            k = f"{r.get('category')}::{r.get('subject')}::{r.get('mode')}"
            latest[k] = r
    order = {f"{c}::{s}::{m}": i for i, (c, s, m, _) in enumerate(use_matrix)}
    cleaned = sorted(
        latest.values(),
        key=lambda r: order.get(f"{r.get('category')}::{r.get('subject')}::{r.get('mode')}", 999),
    )
    use_report.parent.mkdir(parents=True, exist_ok=True)
    use_report.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"ok": row["ok"], "subject": row.get("subject"), "mode": row.get("mode")}


def append_matrix_row_legacy(row: dict) -> dict:
    return append_matrix_row(row)


def main() -> None:
    if len(sys.argv) > 1 and Path(sys.argv[1]).is_file():
        raw = Path(sys.argv[1]).read_bytes().decode("utf-8")
    else:
        raw = sys.stdin.buffer.read().decode("utf-8")
    row = json.loads(raw)
    result = append_matrix_row(row)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
