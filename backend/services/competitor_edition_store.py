"""竞品财报多期次（1.2.3.e）：editions/ + current.json。"""
from __future__ import annotations

import json
import logging
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.config import settings
from backend.services.competitor_report_store import (
    COMPETITOR_SUBDIR,
    RAW_FILENAME,
    SNAPSHOT_FILENAME,
    competitor_dir,
)

logger = logging.getLogger(__name__)

EDITION_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
LEGACY_EDITION_ID = "2025-annual"
CURRENT_FILENAME = "current.json"
EDITIONS_SUBDIR = "editions"
META_FILENAME = "meta.json"

def validate_edition_id(edition_id: str) -> str:
    eid = (edition_id or "").strip()
    if not EDITION_ID_RE.match(eid):
        raise ValueError(
            "edition_id 须匹配 ^[a-z0-9][a-z0-9_-]{0,31}$（如 2025-annual、2026-h1）"
        )
    return eid


def editions_root() -> Path:
    return competitor_dir() / EDITIONS_SUBDIR


def edition_dir(edition_id: str) -> Path:
    return editions_root() / validate_edition_id(edition_id)


def edition_meta_path(edition_id: str) -> Path:
    return edition_dir(edition_id) / META_FILENAME


def edition_snapshot_path(edition_id: str) -> Path:
    return edition_dir(edition_id) / SNAPSHOT_FILENAME


def edition_raw_path(edition_id: str) -> Path:
    return edition_dir(edition_id) / RAW_FILENAME


def edition_history_dir(edition_id: str) -> Path:
    return edition_dir(edition_id) / "history"


def current_path() -> Path:
    return competitor_dir() / CURRENT_FILENAME


def _default_period_label(edition_id: str, kind: str) -> str:
    if edition_id == LEGACY_EDITION_ID or kind == "annual":
        if edition_id.startswith("20") and len(edition_id) >= 4:
            year = edition_id[:4]
            return f"{year} 年报"
        return "年报"
    if kind == "interim":
        if edition_id.startswith("20") and len(edition_id) >= 4:
            return f"{edition_id[:4]} 半年报"
        return "半年报"
    return edition_id


def save_edition_meta(meta: dict[str, Any]) -> dict[str, Any]:
    eid = validate_edition_id(str(meta.get("edition_id") or ""))
    kind = str(meta.get("kind") or "annual").strip().lower()
    if kind not in ("annual", "interim"):
        raise ValueError("kind 须为 annual 或 interim")
    period_label = str(meta.get("period_label") or "").strip() or _default_period_label(eid, kind)
    has_vertical = bool(meta.get("has_vertical", kind == "annual"))
    out: dict[str, Any] = {
        "edition_id": eid,
        "kind": kind,
        "period_label": period_label,
        "has_vertical": has_vertical,
    }
    for key in (
        "notes",
        "uploaded_at",
        "uploaded_by",
        "source_filename",
        "title",
        "company_count",
    ):
        if key in meta and meta[key] is not None:
            out[key] = meta[key]

    d = edition_dir(eid)
    d.mkdir(parents=True, exist_ok=True)
    edition_meta_path(eid).write_text(
        json.dumps(out, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return out


def load_edition_meta(edition_id: str) -> dict[str, Any] | None:
    path = edition_meta_path(edition_id)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def ensure_edition(
    edition_id: str,
    *,
    kind: str = "annual",
    period_label: str | None = None,
    has_vertical: bool | None = None,
) -> dict[str, Any]:
    eid = validate_edition_id(edition_id)
    existing = load_edition_meta(eid)
    if existing:
        return existing
    meta: dict[str, Any] = {
        "edition_id": eid,
        "kind": kind,
        "period_label": period_label or _default_period_label(eid, kind),
        "has_vertical": has_vertical if has_vertical is not None else (kind == "annual"),
    }
    return save_edition_meta(meta)


def get_current() -> str | None:
    path = current_path()
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            eid = str((data or {}).get("edition_id") or "").strip()
            if eid and EDITION_ID_RE.match(eid):
                return eid
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            pass
    # 无 current 时：若仅有一期则用之；多期次按 edition_id 数字友好降序取确定性默认
    ids = [p.name for p in editions_root().iterdir()] if editions_root().is_dir() else []
    ids = [i for i in ids if EDITION_ID_RE.match(i) and edition_dir(i).is_dir()]
    if len(ids) == 1:
        return ids[0]
    if LEGACY_EDITION_ID in ids:
        return LEGACY_EDITION_ID
    if not ids:
        return None
    return sorted(
        ids,
        reverse=True,
        key=lambda x: [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", x)],
    )[0]

def set_current(edition_id: str) -> str:
    eid = validate_edition_id(edition_id)
    if not edition_dir(eid).is_dir():
        raise ValueError(f"期次不存在: {eid}")
    competitor_dir().mkdir(parents=True, exist_ok=True)
    current_path().write_text(
        json.dumps({"edition_id": eid}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return eid


def list_editions() -> list[dict[str, Any]]:
    migrate_legacy_competitor_layout()
    root = editions_root()
    if not root.is_dir():
        return []
    current = get_current()
    out: list[dict[str, Any]] = []
    for child in sorted(root.iterdir(), key=lambda p: p.name):
        if not child.is_dir() or not EDITION_ID_RE.match(child.name):
            continue
        meta = load_edition_meta(child.name) or {
            "edition_id": child.name,
            "kind": "annual" if child.name == LEGACY_EDITION_ID else "interim",
            "period_label": _default_period_label(
                child.name,
                "annual" if child.name == LEGACY_EDITION_ID else "interim",
            ),
            "has_vertical": child.name == LEGACY_EDITION_ID,
        }
        row = dict(meta)
        row["is_current"] = child.name == current
        row["has_snapshot"] = (child / SNAPSHOT_FILENAME).is_file()
        out.append(row)
    return out


def _move_if_exists(src: Path, dest: Path) -> bool:
    if not src.exists():
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return False
    shutil.move(str(src), str(dest))
    return True


def _migrate_legacy_vertical(root: Path, target: Path, result: dict[str, Any]) -> None:
    """将根目录纵向文件迁入 editions/2025-annual；幂等。"""
    if _move_if_exists(root / "vertical.snapshot.json", target / "vertical.snapshot.json"):
        result["actions"].append("move:vertical.snapshot.json")
    if _move_if_exists(root / "vertical_report.md", target / "vertical_report.md"):
        result["actions"].append("move:vertical_report.md")
    for name in ("各公司纵向分析报告.md",):
        if _move_if_exists(root / name, target / name):
            result["actions"].append(f"move:{name}")
    legacy_vertical_dir = root / "vertical"
    target_vertical = target / "vertical"
    if legacy_vertical_dir.is_dir():
        # 迁 pdfs/；ingest 临时任务留根目录（避免打断进行中 job）
        legacy_pdfs = legacy_vertical_dir / "pdfs"
        if legacy_pdfs.is_dir() and not (target_vertical / "pdfs").exists():
            target_vertical.mkdir(parents=True, exist_ok=True)
            shutil.move(str(legacy_pdfs), str(target_vertical / "pdfs"))
            result["actions"].append("move:vertical/pdfs")
        # 根 vertical/ 若只剩 ingest 或已空，不强删 ingest


def migrate_legacy_competitor_layout() -> dict[str, Any]:
    """将根目录单例 Snapshot/纵向迁入 editions/2025-annual；幂等。"""
    root = competitor_dir()
    result: dict[str, Any] = {"migrated": False, "edition_id": LEGACY_EDITION_ID, "actions": []}
    if not root.is_dir():
        return result

    legacy_snap = root / SNAPSHOT_FILENAME
    legacy_raw = root / RAW_FILENAME
    target = edition_dir(LEGACY_EDITION_ID)
    target_snap = target / SNAPSHOT_FILENAME

    needs_horizontal = legacy_snap.is_file() and not target_snap.is_file()
    needs_vertical = (
        ((root / "vertical.snapshot.json").is_file() and not (target / "vertical.snapshot.json").is_file())
        or ((root / "vertical_report.md").is_file() and not (target / "vertical_report.md").is_file())
        or (
            (root / "vertical" / "pdfs").is_dir()
            and not (target / "vertical" / "pdfs").exists()
        )
    )

    if not needs_horizontal and not needs_vertical:
        # 仍确保：若已有 editions 但无 current，补写
        if editions_root().is_dir() and not current_path().is_file():
            eid = get_current()
            if eid:
                set_current(eid)
                result["actions"].append(f"set_current:{eid}")
        result["migrated"] = bool(result["actions"])
        return result

    ensure_edition(
        LEGACY_EDITION_ID,
        kind="annual",
        period_label="2025 年报",
        has_vertical=True,
    )
    if needs_horizontal:
        if _move_if_exists(legacy_snap, target_snap):
            result["actions"].append("move:report.snapshot.json")
        if _move_if_exists(legacy_raw, target / RAW_FILENAME):
            result["actions"].append("move:report.md")
        legacy_hist = root / "history"
        if legacy_hist.is_dir() and not (target / "history").exists():
            shutil.move(str(legacy_hist), str(target / "history"))
            result["actions"].append("move:history")

    if needs_vertical:
        _migrate_legacy_vertical(root, target, result)

    if not current_path().is_file():
        set_current(LEGACY_EDITION_ID)
        result["actions"].append(f"set_current:{LEGACY_EDITION_ID}")

    result["migrated"] = bool(result["actions"])
    if result["migrated"]:
        logger.info("competitor legacy migrate: %s", result["actions"])
    return result
