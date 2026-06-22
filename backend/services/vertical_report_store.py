"""纵向对比报告 MD 读取（uploads/competitor/ 或仓库 uploads/ 蓝本）。"""
from __future__ import annotations

from pathlib import Path

from backend.config import settings
from backend.services.vertical_report_parser import parse_vertical_report

VERTICAL_FILENAME = "vertical_report.md"
REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "vertical_report_minimal.md"


def _candidate_paths() -> list[Path]:
    upload_root = Path(settings.upload_dir)
    if not upload_root.is_absolute():
        upload_root = REPO_ROOT / upload_root
    return [
        upload_root / "competitor" / VERTICAL_FILENAME,
        FIXTURE_PATH,
    ]


def load_vertical_report() -> dict | None:
    for path in _candidate_paths():
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            return parse_vertical_report(text)
    return None
