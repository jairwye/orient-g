"""竞品财报 Snapshot 与 raw MD 文件存储（多期次 editions/，1.2.3.e）。"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.config import settings

COMPETITOR_SUBDIR = "competitor"
RAW_FILENAME = "report.md"
SNAPSHOT_FILENAME = "report.snapshot.json"

# 本地开发 fixture：由 competitor_report_minimal.md 按需解析（不提交大体积 snapshot 产物）
FIXTURE_MD_PATH = (
    Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "competitor_report_minimal.md"
)

_fixture_cache: dict[str, Any] | None = None


def competitor_dir() -> Path:
    return Path(settings.upload_dir) / COMPETITOR_SUBDIR


def raw_path() -> Path:
    """旧单例路径（仅兼容/迁移）；新写入走 edition_raw_path。"""
    return competitor_dir() / RAW_FILENAME


def snapshot_path() -> Path:
    """旧单例路径（仅兼容/迁移）。"""
    return competitor_dir() / SNAPSHOT_FILENAME


def history_dir() -> Path:
    return competitor_dir() / "history"


def _read_snapshot_file(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _load_dev_fixture() -> dict[str, Any] | None:
    global _fixture_cache
    if _fixture_cache is not None:
        return _fixture_cache
    if not FIXTURE_MD_PATH.is_file():
        return None
    from backend.services.competitor_report_parser import parse_markdown

    text = FIXTURE_MD_PATH.read_text(encoding="utf-8")
    snap, _ = parse_markdown(
        text,
        source_filename=FIXTURE_MD_PATH.name,
        uploaded_by="fixture",
    )
    _fixture_cache = snap
    return snap


def _infer_edition_kind(edition_id: str) -> str:
    """从 edition_id 启发式推断 kind；优先识别 annual / h1|h2|interim。"""
    eid = (edition_id or "").strip().lower()
    if eid == "2025-annual" or "annual" in eid:
        return "annual"
    if any(tok in eid for tok in ("h1", "h2", "interim", "semi")):
        return "interim"
    return "interim"


def _resolve_edition_id(edition_id: str | None) -> str | None:
    from backend.services.competitor_edition_store import (
        get_current,
        migrate_legacy_competitor_layout,
        validate_edition_id,
    )

    migrate_legacy_competitor_layout()
    if edition_id:
        return validate_edition_id(edition_id)
    return get_current()


def _annotate_edition(snap: dict[str, Any], edition_id: str) -> dict[str, Any]:
    from backend.services.competitor_edition_store import load_edition_meta

    out = dict(snap)
    meta = dict(out.get("meta") or {})
    em = load_edition_meta(edition_id) or {}
    meta.setdefault("edition_id", edition_id)
    if em.get("kind"):
        meta.setdefault("kind", em["kind"])
    if em.get("period_label"):
        meta.setdefault("period_label", em["period_label"])
    out["meta"] = meta
    return out


def load_snapshot(edition_id: str | None = None) -> dict[str, Any] | None:
    from backend.services.competitor_edition_store import edition_snapshot_path

    eid = _resolve_edition_id(edition_id)
    if eid:
        uploaded = _read_snapshot_file(edition_snapshot_path(eid))
        if uploaded is not None:
            return _annotate_edition(uploaded, eid)
        # 已解析到期次（显式 ?edition= 或 current）：禁止交叉回退到别期/根单例/fixture
        return None

    # 仅「未指定期次且无 current」时兼容根单例 / 开发 fixture（迁移前空库）
    uploaded = _read_snapshot_file(snapshot_path())
    if uploaded is not None:
        return uploaded

    if settings.effective_competitor_fixture_fallback:
        return _load_dev_fixture()
    return None


def is_fixture_snapshot(edition_id: str | None = None) -> bool:
    """当前 load_snapshot 是否来自仓库 fixture（无实际上传）。"""
    from backend.services.competitor_edition_store import edition_snapshot_path

    explicit = bool(edition_id and str(edition_id).strip())
    if explicit:
        return False
    eid = _resolve_edition_id(edition_id)
    if eid:
        # 有 current/解析期次时不以 fixture 冒充
        return False
    if snapshot_path().is_file():
        return False
    return settings.effective_competitor_fixture_fallback and FIXTURE_MD_PATH.is_file()

def snapshot_for_api(edition_id: str | None = None) -> dict[str, Any] | None:
    snap = load_snapshot(edition_id)
    if snap is None:
        return None
    if not is_fixture_snapshot(edition_id):
        return snap
    out = dict(snap)
    meta = dict(out.get("meta") or {})
    meta["data_source"] = "fixture"
    out["meta"] = meta
    return out


def save_snapshot(
    raw_bytes: bytes,
    snapshot: dict[str, Any],
    *,
    edition_id: str | None = None,
    keep_history: bool = True,
) -> str:
    """写入指定期次；返回实际 edition_id。未传 edition_id 时写入 current 或新建 2025-annual。"""
    from backend.services.competitor_edition_store import (
        LEGACY_EDITION_ID,
        edition_history_dir,
        edition_raw_path,
        edition_snapshot_path,
        ensure_edition,
        get_current,
        load_edition_meta,
        save_edition_meta,
        set_current,
        validate_edition_id,
    )

    if edition_id:
        eid = validate_edition_id(edition_id)
    else:
        eid = get_current() or LEGACY_EDITION_ID

    existing = load_edition_meta(eid)
    if existing and existing.get("kind") in ("annual", "interim"):
        kind = str(existing["kind"])
    else:
        kind = _infer_edition_kind(eid)
    ensure_edition(eid, kind=kind)

    snap_meta = dict(snapshot.get("meta") or {})
    snap_meta["edition_id"] = eid
    snap_meta.setdefault("kind", kind)
    snapshot = dict(snapshot)
    snapshot["meta"] = snap_meta

    dest_dir = edition_snapshot_path(eid).parent
    dest_dir.mkdir(parents=True, exist_ok=True)
    edition_raw_path(eid).write_bytes(raw_bytes)
    edition_snapshot_path(eid).write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    em = load_edition_meta(eid) or {"edition_id": eid, "kind": kind}
    em["uploaded_at"] = snap_meta.get("uploaded_at") or datetime.now(timezone.utc).isoformat()
    em["uploaded_by"] = snap_meta.get("uploaded_by")
    em["source_filename"] = snap_meta.get("source_filename")
    em["title"] = snap_meta.get("title")
    em["company_count"] = snap_meta.get("company_count")
    save_edition_meta(em)

    if get_current() is None:
        set_current(eid)

    if keep_history:
        hdir = edition_history_dir(eid)
        hdir.mkdir(parents=True, exist_ok=True)
        ts = (snap_meta.get("uploaded_at") or datetime.now(timezone.utc).isoformat()).replace(":", "-")
        fname = snap_meta.get("source_filename") or "report.md"
        safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in fname)
        (hdir / f"{ts}_{safe}").write_bytes(raw_bytes)

    return eid


def load_meta(edition_id: str | None = None) -> dict[str, Any] | None:
    snap = load_snapshot(edition_id)
    if not snap:
        return None
    meta = dict(snap.get("meta") or {})
    meta["warnings"] = list(snap.get("warnings") or [])
    if is_fixture_snapshot(edition_id):
        meta["data_source"] = "fixture"
    return meta
