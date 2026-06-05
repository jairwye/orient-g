"""返回仍需 MCP 重跑的 subject+mode（最新行 ok:false 或流式未完成）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "backend" / "tests" / "reports" / "finance_matrix_browser_report.json"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from finance_matrix_cases import MATRIX, MODE_LABEL, TIER_EXPECT  # noqa: E402
from finance_matrix_browser_validate import WAIT_CITATIONS_MS  # noqa: E402


def _key(category: str, subject: str, mode: str) -> str:
    return f"{category}::{subject}::{mode}"


def latest_rows() -> dict[str, dict]:
    if not REPORT.is_file():
        return {}
    rows = json.loads(REPORT.read_text(encoding="utf-8"))
    out: dict[str, dict] = {}
    for r in rows:
        if isinstance(r, dict) and r.get("subject"):
            out[_key(str(r["category"]), str(r["subject"]), str(r["mode"]))] = r
    return out


def retry_pending() -> list[tuple[str, str, str, str]]:
    latest = latest_rows()
    out: list[tuple[str, str, str, str]] = []
    for cat, subj, mode, query in MATRIX:
        k = _key(cat, subj, mode)
        row = latest.get(k)
        if row is None or row.get("ok") is not True:
            out.append((cat, subj, mode, query))
    return out


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "count":
        p = retry_pending()
        latest = latest_rows()
        ok_n = sum(1 for r in latest.values() if r.get("ok") is True)
        print(
            json.dumps(
                {
                    "ok_pass": ok_n,
                    "retry_pending": len(p),
                    "total": len(MATRIX),
                },
                ensure_ascii=False,
            )
        )
        return
    if len(sys.argv) > 1 and sys.argv[1] == "next":
        p = retry_pending()
        if not p:
            print("null")
            return
        cat, subj, mode, query = p[0]
        print(
            json.dumps(
                {
                    "category": cat,
                    "subject": subj,
                    "mode": mode,
                    "mode_label": MODE_LABEL[mode],
                    "tier_expect": TIER_EXPECT[mode],
                    "query": query,
                    "wait_citations_ms": WAIT_CITATIONS_MS[mode],
                    "poll_interval_ms": 15_000,
                    "poll_stable_rounds": 2,
                    "cooldown_ms": 5_000,
                },
                ensure_ascii=False,
            )
        )
        return
    for row in retry_pending():
        print("\t".join(row[:3]))


if __name__ == "__main__":
    main()
