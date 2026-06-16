#!/usr/bin/env python3
"""从蓝本 MD 同步竞品财报 snapshot 到 fixture 与 uploads/competitor/（页面运行时数据源）。

用法（仓库根目录）：
  python backend/scripts/sync_competitor_from_blueprint.py
  python backend/scripts/sync_competitor_from_blueprint.py --md uploads/行业财报汇析-2025年_数据文档_YYCQ版.md
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MD = REPO_ROOT / "uploads" / "行业财报汇析-2025年_数据文档_YYCQ版.md"
FIXTURE_SNAPSHOT = (
    REPO_ROOT / "backend" / "tests" / "fixtures" / "competitor_report_yycq.snapshot.json"
)

sys.path.insert(0, str(REPO_ROOT))
from backend.services.competitor_report_parser import parse_markdown  # noqa: E402
from backend.services.competitor_report_store import save_snapshot  # noqa: E402

DUAL_CELL_RE = re.compile(r"^[\d,]+(\.\d+)?\s+[\d,]+(\.\d+)?$")
ANCHOR_TABLE_RE = re.compile(r"^#{1,3}\s+(sec-\d{2}(?:-\d+)?)\b")


def _scan_dual_values(md_text: str) -> list[str]:
    issues: list[str] = []
    current_anchor = ""
    for i, line in enumerate(md_text.splitlines(), 1):
        m = ANCHOR_TABLE_RE.match(line.strip())
        if m:
            current_anchor = m.group(1)
        if not line.strip().startswith("|") or "---" in line:
            continue
        cells = [c.strip() for c in line.split("|")[1:-1]]
        if len(cells) < 2:
            continue
        for cell in cells[1:]:
            if DUAL_CELL_RE.match(cell.replace(" ", " ").strip()):
                issues.append(f"L{i} [{current_anchor}] merged cell: {cell!r}")
    return issues


def _spot_checks(snapshot: dict) -> list[str]:
    """sec-06+ 关键字段与蓝本一致性的快速断言。"""
    checks: list[tuple[str, str, str, float]] = [
        ("sec-06-1", "货币资金(万)", "三七互娱", 412_355.0),
        ("sec-06-1", "货币资金(万)", "完美世界", 354_702.0),
        ("sec-06-1", "短期借款(万)", "三七互娱", 396_383.0),
        ("sec-07-1", "营业收入(万)", "三七互娱", 1_596_571.0),
        ("sec-07-1", "净利润(万)", "YYCQ", 5_698.0),
        ("sec-08-2", "净利润(万)", "三七互娱", 289_895.0),
        ("sec-09-2", "广告推广费(万)", "三七互娱", 721_759.0),
        ("sec-09-6", "人民币(万)", "三七互娱", 329_124.0),
    ]
    errors: list[str] = []
    blocks_by_anchor: dict[str, dict] = {}
    for sec in snapshot.get("sections", []):
        for block in sec.get("blocks", []):
            if block.get("kind") == "table" and block.get("anchor"):
                blocks_by_anchor[block["anchor"]] = block

    for anchor, subject, col, expected in checks:
        block = blocks_by_anchor.get(anchor)
        if not block:
            errors.append(f"missing table {anchor}")
            continue
        h0 = block["headers"][0]
        row = next((r for r in block["rows"] if str(r.get(h0)) == subject), None)
        if not row:
            errors.append(f"{anchor} row {subject!r} not found")
            continue
        actual = row.get(col)
        if actual is None or abs(float(actual) - expected) > 0.5:
            errors.append(f"{anchor} {subject} {col}: got {actual!r}, want {expected}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync competitor report from blueprint MD")
    parser.add_argument("--md", type=Path, default=DEFAULT_MD, help="Blueprint markdown path")
    parser.add_argument("--skip-upload-dir", action="store_true", help="Only update fixture JSON")
    args = parser.parse_args()

    md_path = args.md.resolve()
    if not md_path.is_file():
        print(f"FAIL: blueprint not found: {md_path}", file=sys.stderr)
        return 1

    raw = md_path.read_bytes()
    md_text = raw.decode("utf-8")
    dual = _scan_dual_values(md_text)
    if dual:
        print("FAIL: blueprint still has merged YYCQ cells:", file=sys.stderr)
        for d in dual:
            print(f"  {d}", file=sys.stderr)
        return 1

    snapshot, warnings = parse_markdown(
        md_text,
        source_filename=md_path.name,
        uploaded_by="sync_competitor_from_blueprint",
    )
    if warnings:
        print(f"WARN: parser warnings ({len(warnings)}):", file=sys.stderr)
        for w in warnings:
            print(f"  {w}", file=sys.stderr)

    spot = _spot_checks(snapshot)
    if spot:
        print("FAIL: spot checks:", file=sys.stderr)
        for e in spot:
            print(f"  {e}", file=sys.stderr)
        return 1

    FIXTURE_SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE_SNAPSHOT.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"OK: fixture -> {FIXTURE_SNAPSHOT.relative_to(REPO_ROOT)}")

    if not args.skip_upload_dir:
        save_snapshot(raw, snapshot, keep_history=True)
        print(f"OK: runtime -> uploads/competitor/report.snapshot.json (+ report.md)")

    print(
        f"OK: {len(snapshot.get('sections', []))} sections, "
        f"{len(snapshot.get('companies', []))} companies, warnings={len(warnings)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
