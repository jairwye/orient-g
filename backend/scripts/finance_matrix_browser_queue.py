"""页面矩阵队列：跳过 report 中已有 subject+mode 组合。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "backend" / "tests" / "reports" / "finance_matrix_browser_report.json"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from finance_matrix_cases import MATRIX, MODE_LABEL, TIER_EXPECT  # noqa: E402


def _key(category: str, subject: str, mode: str) -> str:
    return f"{category}::{subject}::{mode}"


def done_keys() -> set[str]:
    if not REPORT.is_file():
        return set()
    rows = json.loads(REPORT.read_text(encoding="utf-8"))
    out: set[str] = set()
    for r in rows:
        if not isinstance(r, dict):
            continue
        k = _key(str(r.get("category", "")), str(r.get("subject", "")), str(r.get("mode", "")))
        # 已实测（含 ok:false）不再重跑，避免 Hermes 回退档反复卡住队列
        if r.get("subject") and r.get("mode"):
            out.add(k)
    return out


def pending() -> list[tuple[str, str, str, str]]:
    done = done_keys()
    out: list[tuple[str, str, str, str]] = []
    for cat, subj, mode, query in MATRIX:
        if _key(cat, subj, mode) not in done:
            out.append((cat, subj, mode, query))
    return out


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "count":
        p = pending()
        rows = json.loads(REPORT.read_text(encoding="utf-8")) if REPORT.is_file() else []
        ok_n = sum(1 for r in rows if isinstance(r, dict) and r.get("ok") is True)
        attempted = len(done_keys())
        print(
            json.dumps(
                {"ok_pass": ok_n, "attempted": attempted, "pending": len(p), "total": len(MATRIX)},
                ensure_ascii=False,
            )
        )
        return
    if len(sys.argv) > 1 and sys.argv[1] == "next":
        p = pending()
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
                    "wait_ms": 300000 if mode == "fast" else 900000,
                },
                ensure_ascii=False,
            )
        )
        return
    for row in pending():
        print("\t".join(row[:3]) + "\t" + row[3][:40])


if __name__ == "__main__":
    main()
