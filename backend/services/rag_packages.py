from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote

from sqlalchemy import text

from backend.config import settings
from backend.database import get_db


ExportProfile = Literal[
    "standard",
    "openwebui",
    "cn_kb",
    # aliases (历史/便捷入口，实际与 cn_kb 同构)
    "doubao",
    "cherrystudio",
    "mita",
    "qianwen",
    "ima",
    "chatbot",
]


def normalize_profile(profile: str) -> tuple[Literal["standard", "openwebui", "cn_kb"], str]:
    """
    将输入 profile 归一到 3 类产物：
    - standard：完整标准包（raw/archive/kb）
    - openwebui：为 Open WebUI 习惯优化（sections + merged + manifest）
    - cn_kb：中文语境下常见“带知识库的 AI 产品”的通用包（本质同上）
    返回：(normalized, display_name)
    """
    p = (profile or "standard").strip().lower()
    if p == "standard":
        return "standard", "标准包"
    if p == "openwebui":
        return "openwebui", "Open WebUI"
    if p in {"cn_kb", "doubao", "cherrystudio", "mita", "qianwen", "ima", "chatbot"}:
        label = {
            "cn_kb": "通用中文AI知识库",
            "doubao": "豆包（通用包）",
            "cherrystudio": "CherryStudio（通用包）",
            "mita": "秘塔（通用包）",
            "qianwen": "千问（通用包）",
            "ima": "ima（通用包）",
            "chatbot": "ChatBot（通用包）",
        }.get(p, "通用中文AI知识库")
        return "cn_kb", label
    # fallback：未知 profile 默认走通用包（避免前端/用户输入新工具名导致 400）
    return "cn_kb", "通用中文AI知识库"


def _attachment_content_disposition(filename: str) -> str:
    """HTTP 响应头须 latin-1；中文文件名用 filename* (RFC 5987)。"""
    safe = (filename or "export.zip").replace('"', "'").replace("\\", "_")
    ascii_fallback = re.sub(r"[^\x20-\x7E]+", "_", safe).strip("_") or "export.zip"
    encoded = quote(safe, safe="")
    return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{encoded}"


def _export_base_label(pkg: dict[str, Any]) -> str:
    """Use package display name (PDF filename) for export paths; fallback to package_id."""
    name = str(pkg.get("name") or "").strip()
    package_id = str(pkg.get("package_id") or "package")
    if not name:
        return package_id
    safe = re.sub(r'[<>:"/\\|?*]+', "_", name).strip()[:80]
    return safe or package_id


def _pkg_row(tenant_id: str, package_id: str) -> dict[str, Any] | None:
    with get_db() as db:
        row = db.execute(
            text(
                """
                SELECT package_id, name, manifest_json, storage_path, owner_username, created_at, created_by_task_id
                FROM kb_rag_packages
                WHERE tenant_id=:t AND package_id=:p
                """
            ),
            {"t": tenant_id, "p": package_id},
        ).fetchone()
    if not row:
        return None
    return {
        "package_id": str(row[0]),
        "name": str(row[1] or ""),
        "manifest_json": str(row[2] or "") if row[2] else None,
        "storage_path": str(row[3] or ""),
        "owner_username": str(row[4] or ""),
        "created_at": row[5].isoformat() if row[5] else None,
        "created_by_task_id": str(row[6] or "") if row[6] else None,
    }


def get_package_detail(tenant_id: str, package_id: str) -> dict[str, Any] | None:
    p = _pkg_row(tenant_id, package_id)
    if not p:
        return None
    manifest = None
    if p.get("manifest_json"):
        try:
            manifest = json.loads(p["manifest_json"])
        except Exception:
            manifest = None
    abs_root = Path(settings.upload_dir).resolve() / (p.get("storage_path") or "")
    kb_manifest = abs_root / "kb" / "manifest.json"
    if manifest is None and kb_manifest.exists():
        try:
            manifest = json.loads(kb_manifest.read_text(encoding="utf-8"))
        except Exception:
            manifest = None
    sections_dir = abs_root / "kb" / "sections"
    sections: list[dict[str, Any]] = []
    if sections_dir.exists():
        for f in sorted(sections_dir.glob("*.md")):
            sections.append(
                {
                    "filename": f.name,
                    "size_bytes": f.stat().st_size,
                }
            )
    return {
        **p,
        "manifest": manifest,
        "paths": {
            "root": str(abs_root),
            "raw": str(abs_root / "raw"),
            "archive": str(abs_root / "archive"),
            "kb": str(abs_root / "kb"),
        },
        "sections": sections,
    }


def delete_package(tenant_id: str, package_id: str) -> bool:
    p = _pkg_row(tenant_id, package_id)
    if not p:
        return False
    with get_db() as db:
        db.execute(text("DELETE FROM kb_rag_packages WHERE tenant_id=:t AND package_id=:p"), {"t": tenant_id, "p": package_id})
    # best-effort delete disk folder
    try:
        abs_root = Path(settings.upload_dir).resolve() / (p.get("storage_path") or "")
        if abs_root.exists():
            import shutil

            shutil.rmtree(abs_root, ignore_errors=True)
    except Exception:
        pass
    return True


def _read_text_safe(p: Path, max_bytes: int = 2_000_000) -> str:
    raw = p.read_bytes()
    if len(raw) > max_bytes:
        raw = raw[:max_bytes]
    return raw.decode("utf-8", errors="replace")


def export_package_zip(tenant_id: str, package_id: str, profile: ExportProfile) -> tuple[bytes, str]:
    """
    返回 (zip_bytes, download_filename)
    """
    p = _pkg_row(tenant_id, package_id)
    if not p:
        raise FileNotFoundError("package not found")
    abs_root = Path(settings.upload_dir).resolve() / (p.get("storage_path") or "")
    kb_dir = abs_root / "kb"
    sections_dir = kb_dir / "sections"
    archive_md = abs_root / "archive" / "full.md"
    archive_json = abs_root / "archive" / "full.json"
    kb_manifest = kb_dir / "manifest.json"

    def add_file(z: zipfile.ZipFile, src: Path, arc: str):
        if src.exists() and src.is_file():
            z.write(src, arcname=arc)

    mem = io.BytesIO()
    normalized, display = normalize_profile(str(profile))
    export_base = _export_base_label(p)
    with zipfile.ZipFile(mem, "w", compression=zipfile.ZIP_DEFLATED) as z:
        if normalized == "standard":
            # 完整标准包结构（raw/archive/kb）
            for sub in ("raw", "archive", "kb"):
                d = abs_root / sub
                if not d.exists():
                    continue
                for f in d.rglob("*"):
                    if f.is_file():
                        rel = f.relative_to(abs_root).as_posix()
                        z.write(f, arcname=rel)
        else:
            # 兼容外部端：以 Markdown 分段文件为主（多客户端通吃）
            base = f"{export_base}_{normalized}"
            # manifest 作为元信息附带
            add_file(z, kb_manifest, f"{base}/manifest.json")

            # Open WebUI: 多文件 md 更稳（且单文件过大可能失败），按 sections 输出
            # 豆包/CherryStudio：普遍支持上传 md 文件/文件夹，此处也按 sections 输出
            if sections_dir.exists():
                for f in sorted(sections_dir.glob("*.md")):
                    add_file(z, f, f"{base}/sections/{f.name}")

            # 额外输出一个 merged.md，便于只支持单文件导入的客户端（可选）
            if archive_md.exists():
                merged = _read_text_safe(archive_md, max_bytes=8_000_000)
                z.writestr(f"{base}/merged.md", merged)

            # 有些端希望保留结构化 json 作为证据或二次加工
            if archive_json.exists():
                add_file(z, archive_json, f"{base}/archive/full.json")

            # profile 说明文件
            note = {
                "profile": normalized,
                "profile_display": display,
                "recommendation": "优先上传 sections/*.md（避免单文件过大）。如目标仅支持单文件，可上传 merged.md。",
                "common_products_cn": [
                    "秘塔",
                    "豆包",
                    "通义千问",
                    "ima",
                    "各类带知识库的 ChatBot 客户端",
                ],
            }
            z.writestr(f"{base}/README.json", json.dumps(note, ensure_ascii=False, indent=2))

    mem.seek(0)
    filename = f"{export_base}_{normalized}.zip"
    return mem.read(), filename


def preview_text(
    tenant_id: str,
    package_id: str,
    *,
    kind: Literal["merged", "section"],
    filename: str | None = None,
    max_bytes: int = 200_000,
) -> dict[str, Any]:
    p = _pkg_row(tenant_id, package_id)
    if not p:
        raise FileNotFoundError("package not found")
    abs_root = Path(settings.upload_dir).resolve() / (p.get("storage_path") or "")
    if kind == "merged":
        target = abs_root / "archive" / "full.md"
    else:
        safe = Path(filename or "").name
        if not safe.endswith(".md"):
            raise ValueError("invalid filename")
        target = abs_root / "kb" / "sections" / safe
    if not target.exists() or not target.is_file():
        raise FileNotFoundError("file not found")
    text = _read_text_safe(target, max_bytes=max_bytes)
    return {"ok": True, "kind": kind, "filename": target.name, "truncated": target.stat().st_size > max_bytes, "text": text}

