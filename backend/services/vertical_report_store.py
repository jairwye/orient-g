"""纵向对比报告 MD 读取与存储（{upload_dir}/competitor/vertical_report.md）。"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.config import settings
from backend.services.competitor_report_store import competitor_dir, history_dir
from backend.services.vertical_report_parser import parse_vertical_report

VERTICAL_FILENAME = "vertical_report.md"
# 内网蓝本常用文件名（gitignore；开发机可手动放置，生产须走财务后台上传）
VERTICAL_BLUEPRINT_NAMES = (
    VERTICAL_FILENAME,
    "各公司纵向分析报告.md",
)
REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "vertical_report_minimal.md"


def vertical_md_path() -> Path:
    return competitor_dir() / VERTICAL_FILENAME


def _candidate_paths(*, include_fixture: bool) -> list[Path]:
    upload_root = Path(settings.upload_dir)
    if not upload_root.is_absolute():
        upload_root = REPO_ROOT / upload_root
    paths: list[Path] = []
    paths.append(upload_root / "competitor" / VERTICAL_FILENAME)
    for name in VERTICAL_BLUEPRINT_NAMES:
        if name == VERTICAL_FILENAME:
            continue
        paths.append(upload_root / "competitor" / name)
        paths.append(upload_root / name)
    if include_fixture:
        paths.append(FIXTURE_PATH)
    return paths


def _annotate_doc(doc: dict[str, Any], *, path: Path) -> dict[str, Any]:
    out = dict(doc)
    meta = dict(out.get("meta") or {})
    if path == FIXTURE_PATH:
        meta["data_source"] = "fixture"
    out["meta"] = meta
    return out


def load_vertical_report() -> dict[str, Any] | None:
    include_fixture = settings.effective_competitor_fixture_fallback
    for path in _candidate_paths(include_fixture=include_fixture):
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            doc = parse_vertical_report(text)
            return _annotate_doc(doc, path=path)
    return None


def is_fixture_vertical_report() -> bool:
    if vertical_md_path().is_file():
        return False
    include_fixture = settings.effective_competitor_fixture_fallback
    return include_fixture and FIXTURE_PATH.is_file()


def save_vertical_report(
    raw_bytes: bytes,
    *,
    source_filename: str,
    uploaded_by: str,
) -> dict[str, Any]:
    text = raw_bytes.decode("utf-8")
    doc = parse_vertical_report(text)
    now = datetime.now(timezone.utc).isoformat()
    meta = dict(doc.get("meta") or {})
    meta.update(
        {
            "source_filename": source_filename,
            "uploaded_by": uploaded_by,
            "uploaded_at": now,
        }
    )
    doc["meta"] = meta

    d = competitor_dir()
    d.mkdir(parents=True, exist_ok=True)
    vertical_md_path().write_bytes(raw_bytes)

    history_dir().mkdir(parents=True, exist_ok=True)
    ts = now.replace(":", "-")
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in source_filename)
    hist = history_dir() / f"{ts}_vertical_{safe}"
    hist.write_bytes(raw_bytes)

    return doc


def load_vertical_meta() -> dict[str, Any] | None:
    doc = load_vertical_report()
    if not doc:
        return None
    meta = dict(doc.get("meta") or {})
    meta["warnings"] = list(doc.get("warnings") or [])
    meta["company_count"] = len(doc.get("companies") or [])
    if is_fixture_vertical_report():
        meta["data_source"] = "fixture"
    return meta
