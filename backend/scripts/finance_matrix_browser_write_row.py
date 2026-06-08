#!/usr/bin/env python3
"""Merge queue case + poll extract JSON → _browser_row_tmp.json for append."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "backend" / "tests" / "reports" / "_browser_row_tmp.json"
_SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS))
from finance_matrix_browser_retry_queue import retry_pending  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: write_row.py <poll_state.json> [notes]", file=sys.stderr)
        sys.exit(1)
    poll = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    notes = sys.argv[2] if len(sys.argv) > 2 else "serial loop"
    if poll.get("category") and poll.get("subject") and poll.get("mode"):
        cat = str(poll["category"])
        subj = str(poll["subject"])
        mode = str(poll["mode"])
        query = str(poll.get("query") or "")
    else:
        pending = retry_pending()
        if not pending:
            print("null")
            return
        cat, subj, mode, query = pending[0]
    row = {
        "category": cat,
        "subject": subj,
        "mode": mode,
        "query": query,
        "tier_line": poll.get("tier_line", ""),
        "citations": poll.get("citations", 0),
        "notes": notes,
        "extract": poll.get("extract") or {},
        "console_depth_error": bool(poll.get("console_depth_error")),
    }
    TMP.write_text(json.dumps(row, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"written": str(TMP), "case": f"{cat}/{subj}/{mode}"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
