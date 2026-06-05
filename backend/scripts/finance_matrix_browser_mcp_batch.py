#!/usr/bin/env python3
"""Batch-append matrix rows from a JSON lines file produced by MCP extract steps.

Each line: full row dict (category, subject, mode, query, tier_line, extract, citations, ...).
Usage:
  python finance_matrix_browser_mcp_batch.py rows.jsonl
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APPEND = Path(__file__).resolve().parent / "finance_matrix_browser_append.py"
TMP = ROOT / "backend" / "tests" / "reports" / "_browser_row_tmp.json"


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if not path or not path.is_file():
        print("usage: finance_matrix_browser_mcp_batch.py <rows.jsonl>", file=sys.stderr)
        sys.exit(1)
    py = sys.executable
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        TMP.write_text(line + "\n", encoding="utf-8")
        subprocess.run([py, str(APPEND), str(TMP)], check=True, cwd=str(ROOT))


if __name__ == "__main__":
    main()
