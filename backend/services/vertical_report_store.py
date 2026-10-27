"""纵向对比报告 MD 读取与存储（按 edition；兼容根目录旧路径）。"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.config import settings
from backend.services.competitor_edition_store import (
    LEGACY_EDITION_ID,
    edition_dir,
    edition_history_dir,
    get_current,
    load_edition_meta,
    validate_edition_id,
)
from backend.services.competitor_report_store import competitor_dir
from backend.services.vertical_report_parser import parse_vertical_report

VERTICAL_FILENAME = "vertical_report.md"
VERTICAL_SNAPSHOT_FILENAME = "vertical.snapshot.json"
# 内网蓝本常用文件名（gitignore；开发机可手动放置，生产须走财务后台上传）
VERTICAL_BLUEPRINT_NAMES = (
    VERTICAL_FILENAME,
    "各公司纵向分析报告.md",
)
REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "vertical_report_minimal.md"


class VerticalNotAllowedError(Exception):
    """期次 has_vertical=false 时拒绝纵向读写。"""

    def __init__(self, detail: str = "no_vertical", *, edition_id: str | None = None):
        self.detail = detail
        self.edition_id = edition_id
        super().__init__(detail)


def resolve_vertical_edition_id(edition_id: str | None = None) -> str | None:
    if edition_id:
        return validate_edition_id(edition_id)
    return get_current()


def assert_edition_allows_vertical(edition_id: str | None) -> str | None:
    """校验期次允许纵向；返回规范化 edition_id（无期次时返回 None，允许 fixture/空库）。"""
    eid = resolve_vertical_edition_id(edition_id)
    if not eid:
        return None
    meta = load_edition_meta(eid)
    if meta is not None and meta.get("has_vertical") is False:
        raise VerticalNotAllowedError("no_vertical", edition_id=eid)
    return eid


def vertical_md_path(edition_id: str | None = None) -> Path:
    eid = resolve_vertical_edition_id(edition_id)
    if eid:
        return edition_dir(eid) / VERTICAL_FILENAME
    return competitor_dir() / VERTICAL_FILENAME


def vertical_snapshot_path(edition_id: str | None = None) -> Path:
    eid = resolve_vertical_edition_id(edition_id)
    if eid:
        return edition_dir(eid) / VERTICAL_SNAPSHOT_FILENAME
    return competitor_dir() / VERTICAL_SNAPSHOT_FILENAME


def _legacy_root_snapshot() -> Path:
    return competitor_dir() / VERTICAL_SNAPSHOT_FILENAME


def _legacy_root_md() -> Path:
    return competitor_dir() / VERTICAL_FILENAME


def _candidate_paths(edition_id: str | None, *, include_fixture: bool) -> list[Path]:
    upload_root = Path(settings.upload_dir)
    if not upload_root.is_absolute():
        upload_root = REPO_ROOT / upload_root
    paths: list[Path] = []
    eid = resolve_vertical_edition_id(edition_id)
    if eid:
        ed_root = edition_dir(eid)
        paths.append(ed_root / VERTICAL_FILENAME)
        for name in VERTICAL_BLUEPRINT_NAMES:
            if name != VERTICAL_FILENAME:
                paths.append(ed_root / name)
        # 兼容：2025-annual / 未迁完时读根目录旧纵向
        if eid == LEGACY_EDITION_ID:
            paths.append(upload_root / "competitor" / VERTICAL_FILENAME)
            for name in VERTICAL_BLUEPRINT_NAMES:
                if name != VERTICAL_FILENAME:
                    paths.append(upload_root / "competitor" / name)
                    paths.append(upload_root / name)
    else:
        paths.append(upload_root / "competitor" / VERTICAL_FILENAME)
        for name in VERTICAL_BLUEPRINT_NAMES:
            if name != VERTICAL_FILENAME:
                paths.append(upload_root / "competitor" / name)
                paths.append(upload_root / name)
    if include_fixture:
        paths.append(FIXTURE_PATH)
    return paths


def _annotate_doc(doc: dict[str, Any], *, path: Path, edition_id: str | None) -> dict[str, Any]:
    out = dict(doc)
    meta = dict(out.get("meta") or {})
    if path == FIXTURE_PATH:
        meta["data_source"] = "fixture"
    if edition_id:
        meta.setdefault("edition_id", edition_id)
    out["meta"] = meta
    return out


def _read_snapshot_file(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None


def save_vertical_snapshot(snapshot: dict[str, Any], *, edition_id: str | None = None) -> None:
    eid = assert_edition_allows_vertical(edition_id)
    if not eid:
        raise ValueError("请指定 edition_id（或先设置 current 期次）")
    path = vertical_snapshot_path(eid)
    path.parent.mkdir(parents=True, exist_ok=True)
    meta = dict(snapshot.get("meta") or {})
    meta["edition_id"] = eid
    out = dict(snapshot)
    out["meta"] = meta
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")


def load_vertical_report(edition_id: str | None = None) -> dict[str, Any] | None:
    eid = assert_edition_allows_vertical(edition_id)

    snap_paths: list[Path] = []
    if eid:
        snap_paths.append(vertical_snapshot_path(eid))
        if eid == LEGACY_EDITION_ID:
            snap_paths.append(_legacy_root_snapshot())
    else:
        snap_paths.append(_legacy_root_snapshot())

    for sp in snap_paths:
        snap = _read_snapshot_file(sp)
        if snap is not None:
            return _annotate_doc(snap, path=sp, edition_id=eid)

    include_fixture = settings.effective_competitor_fixture_fallback
    for path in _candidate_paths(eid, include_fixture=include_fixture):
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            doc = parse_vertical_report(text)
            return _annotate_doc(doc, path=path, edition_id=eid)
    return None


def is_fixture_vertical_report(edition_id: str | None = None) -> bool:
    try:
        eid = assert_edition_allows_vertical(edition_id)
    except VerticalNotAllowedError:
        return False
    if eid and vertical_snapshot_path(eid).is_file():
        return False
    if eid == LEGACY_EDITION_ID and _legacy_root_snapshot().is_file():
        return False
    if eid and vertical_md_path(eid).is_file():
        return False
    if eid == LEGACY_EDITION_ID and _legacy_root_md().is_file():
        return False
    if not eid and (_legacy_root_snapshot().is_file() or _legacy_root_md().is_file()):
        return False
    include_fixture = settings.effective_competitor_fixture_fallback
    return include_fixture and FIXTURE_PATH.is_file()


def save_vertical_report(
    raw_bytes: bytes,
    *,
    source_filename: str,
    uploaded_by: str,
    edition_id: str | None = None,
) -> dict[str, Any]:
    eid = assert_edition_allows_vertical(edition_id)
    if not eid:
        raise ValueError("请指定 edition_id（如 2025-annual）")

    text = raw_bytes.decode("utf-8")
    doc = parse_vertical_report(text)
    now = datetime.now(timezone.utc).isoformat()
    meta = dict(doc.get("meta") or {})
    meta.update(
        {
            "source_filename": source_filename,
            "uploaded_by": uploaded_by,
            "uploaded_at": now,
            "edition_id": eid,
        }
    )
    doc["meta"] = meta

    d = edition_dir(eid)
    d.mkdir(parents=True, exist_ok=True)
    vertical_md_path(eid).write_bytes(raw_bytes)
    save_vertical_snapshot(doc, edition_id=eid)

    hdir = edition_history_dir(eid)
    hdir.mkdir(parents=True, exist_ok=True)
    ts = now.replace(":", "-")
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in source_filename)
    hist = hdir / f"{ts}_vertical_{safe}"
    hist.write_bytes(raw_bytes)

    return doc


def load_vertical_meta(edition_id: str | None = None) -> dict[str, Any] | None:
    doc = load_vertical_report(edition_id)
    if not doc:
        return None
    meta = dict(doc.get("meta") or {})
    meta["warnings"] = list(doc.get("warnings") or [])
    meta["company_count"] = len(doc.get("companies") or [])
    if is_fixture_vertical_report(edition_id):
        meta["data_source"] = "fixture"
    return meta
