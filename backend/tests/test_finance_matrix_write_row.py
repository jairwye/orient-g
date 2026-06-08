"""finance_matrix_browser_write_row：--only 抽测时不得依赖 retry_pending。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = ROOT / "backend" / "scripts"
sys.path.insert(0, str(_SCRIPTS))

import finance_matrix_browser_write_row as write_row  # noqa: E402


def test_write_row_uses_poll_case_when_retry_queue_empty(tmp_path: Path, monkeypatch) -> None:
    out_tmp = tmp_path / "_browser_row_tmp.json"
    monkeypatch.setattr(write_row, "TMP", out_tmp)

    poll = {
        "category": "pnl",
        "subject": "研发费用",
        "mode": "deep",
        "query": "出一份华清25、24两年研发费用明细的对比分析报告",
        "tier_line": "执行过程(Tier 2（Hermes 深度） · 深度（Hermes 全编排）)",
        "citations": 12,
        "extract": {"len": 1200, "hasMoney": True},
        "console_depth_error": False,
    }
    poll_file = tmp_path / "poll.json"
    poll_file.write_text(json.dumps(poll, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(
        sys,
        "argv",
        ["finance_matrix_browser_write_row.py", str(poll_file), "test-notes"],
    )
    write_row.main()

    row = json.loads(out_tmp.read_text(encoding="utf-8"))
    assert row["subject"] == "研发费用"
    assert row["mode"] == "deep"
    assert row["notes"] == "test-notes"
