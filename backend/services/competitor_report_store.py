"""竞品财报 Snapshot 与 raw MD 文件存储（{upload_dir}/competitor/）。"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.config import settings

COMPETITOR_SUBDIR = "competitor"
RAW_FILENAME = "report.md"
SNAPSHOT_FILENAME = "report.snapshot.json"

# 由 uploads/行业财报汇析-2025年_数据文档_YYCQ版.md 解析生成，供无上传数据时 UI 开发/预览
FIXTURE_SNAPSHOT_PATH = (
    Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "competitor_report_yycq.snapshot.json"
)


def competitor_dir() -> Path:
    return Path(settings.upload_dir) / COMPETITOR_SUBDIR


def raw_path() -> Path:
    return competitor_dir() / RAW_FILENAME


def snapshot_path() -> Path:
    return competitor_dir() / SNAPSHOT_FILENAME


def history_dir() -> Path:
    return competitor_dir() / "history"


def _read_snapshot_file(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_snapshot() -> dict[str, Any] | None:
    uploaded = _read_snapshot_file(snapshot_path())
    if uploaded is not None:
        return uploaded
    if settings.effective_competitor_fixture_fallback:
        return _read_snapshot_file(FIXTURE_SNAPSHOT_PATH)
    return None


def is_fixture_snapshot() -> bool:
    """当前 load_snapshot 是否来自仓库 fixture（无实际上传）。"""
    if snapshot_path().is_file():
        return False
    return settings.effective_competitor_fixture_fallback and FIXTURE_SNAPSHOT_PATH.is_file()


def snapshot_for_api() -> dict[str, Any] | None:
    snap = load_snapshot()
    if snap is None:
        return None
    if not is_fixture_snapshot():
        return snap
    out = dict(snap)
    meta = dict(out.get("meta") or {})
    meta["data_source"] = "fixture"
    out["meta"] = meta
    return out


def save_snapshot(raw_bytes: bytes, snapshot: dict[str, Any], *, keep_history: bool = True) -> None:
    d = competitor_dir()
    d.mkdir(parents=True, exist_ok=True)
    raw_path().write_bytes(raw_bytes)
    snapshot_path().write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if keep_history:
        history_dir().mkdir(parents=True, exist_ok=True)
        meta = snapshot.get("meta") or {}
        ts = (meta.get("uploaded_at") or datetime.now(timezone.utc).isoformat()).replace(":", "-")
        fname = meta.get("source_filename") or "report.md"
        safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in fname)
        hist = history_dir() / f"{ts}_{safe}"
        hist.write_bytes(raw_bytes)


def load_meta() -> dict[str, Any] | None:
    snap = load_snapshot()
    if not snap:
        return None
    meta = dict(snap.get("meta") or {})
    meta["warnings"] = list(snap.get("warnings") or [])
    if is_fixture_snapshot():
        meta["data_source"] = "fixture"
    return meta
