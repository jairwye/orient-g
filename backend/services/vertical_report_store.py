"""纵向对比报告 MD 读取（uploads/competitor/ 或仓库 uploads/ 蓝本）。"""
from __future__ import annotations

from pathlib import Path

from backend.config import settings
from backend.services.vertical_report_parser import parse_vertical_report

VERTICAL_FILENAME = "vertical_report.md"
# 内网蓝本常用文件名（gitignore，优先于测试 fixture）
VERTICAL_BLUEPRINT_NAMES = (
    VERTICAL_FILENAME,
    "各公司纵向分析报告.md",
)
REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "vertical_report_minimal.md"


def _candidate_paths() -> list[Path]:
    upload_root = Path(settings.upload_dir)
    if not upload_root.is_absolute():
        upload_root = REPO_ROOT / upload_root
    paths: list[Path] = []
    for name in VERTICAL_BLUEPRINT_NAMES:
        paths.append(upload_root / "competitor" / name)
        paths.append(upload_root / name)
    paths.append(FIXTURE_PATH)
    return paths


def load_vertical_report() -> dict | None:
    for path in _candidate_paths():
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            return parse_vertical_report(text)
    return None
