from __future__ import annotations

import hashlib
import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text

from backend.config import settings
from backend.database import get_db
from backend.services.docling_runner import convert_to_md_and_json
from backend.services.kb_tasks import get_task as get_kb_task, update_task
from backend.services._kb_helpers import now_iso as _now_iso, write_text as _write_text, write_json as _write_json


def _root() -> Path:
    return Path(settings.upload_dir).resolve() / "kb_bigpdf_tasks"


def _task_root(tenant_id: str, task_id: str) -> Path:
    return _root() / tenant_id / task_id


def _split_markdown_to_sections(md: str) -> list[dict[str, Any]]:
    import re

    text = (md or "").replace("\r\n", "\n")
    parts = re.split(r"\n(?=#{1,2}\s+)", text)
    out: list[dict[str, Any]] = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        title = ""
        first = p.splitlines()[0].strip()
        if first.startswith("#"):
            title = first.lstrip("#").strip()[:200]
        out.append({"title": title or "section", "text": p})
    if not out:
        out = [{"title": "section", "text": text.strip() or "（空文档）"}]
    return out[:400]


def stage_to_progress(stage: str) -> int:
    m = {
        "queued": 0,
        "parsing": 30,
        "packaging": 70,
        "done": 100,
        "completed": 100,
        "failed": 100,
    }
    return int(m.get(stage, 0))


def _upload_filename_from_task(task: dict[str, Any] | None) -> str:
    if not task:
        return ""
    fn = str(task.get("file_name") or "").strip()
    if fn:
        return fn
    detail = str(task.get("detail") or "").strip()
    if detail and not detail.startswith("folder:") and "user_doc:" not in detail:
        return detail
    return ""


def _upload_filename_from_task_dir(root: Path) -> str:
    meta_path = root / "meta.json"
    if not meta_path.exists():
        return ""
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        return str(meta.get("original_filename") or "").strip()
    except Exception:
        return ""


def _resolve_pdf_title(
    task_record: dict[str, Any] | None,
    root: Path,
    md_text: str,
    raw_path: Path,
) -> str:
    """Resolve display name from uploaded PDF filename, with sensible fallbacks."""
    pdf_title = _upload_filename_from_task(task_record) or _upload_filename_from_task_dir(root)
    if not pdf_title:
        try:
            first_line = md_text.strip().split("\n")[0]
            if first_line.startswith("#"):
                pdf_title = first_line.lstrip("#").strip()[:50]
        except Exception:
            pass
    if not pdf_title:
        pdf_title = raw_path.stem
    return pdf_title


def prepare_task_input(tenant_id: str, task_id: str, filename: str, raw: bytes) -> dict[str, Any]:
    """
    保存原始文件到任务目录，供 worker 异步处理。
    """
    root = _task_root(tenant_id, task_id)
    raw_dir = root / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    safe = Path(filename or "upload.pdf").name.replace("..", "_")
    ext = Path(safe).suffix.lower() or ".pdf"
    raw_name = "original.pdf" if ext == ".pdf" else f"original{ext}"
    raw_path = raw_dir / raw_name
    raw_path.write_bytes(raw)
    _write_json(root / "meta.json", {"original_filename": safe})
    return {
        "task_root": str(root),
        "raw_path": str(raw_path),
        "original_filename": safe,
        "source_hash": hashlib.sha256(raw).hexdigest(),
    }


def _insert_rag_package(
    tenant_id: str,
    *,
    package_id: str,
    name: str,
    manifest: dict[str, Any],
    storage_path: str,
    owner_username: str,
    created_by_task_id: str,
) -> None:
    with get_db() as db:
        db.execute(
            text(
                """
                INSERT INTO kb_rag_packages
                    (package_id, tenant_id, name, manifest_json, storage_path, owner_username, created_by_task_id)
                VALUES
                    (:pid, :tid, :n, :mj, :sp, :ou, :tid2)
                """
            ),
            {
                "pid": package_id,
                "tid": tenant_id,
                "n": name,
                "mj": json.dumps(manifest, ensure_ascii=False),
                "sp": storage_path,
                "ou": owner_username,
                "tid2": created_by_task_id,
            },
        )


def process_bigpdf_task(tenant_id: str, task_id: str, owner_username: str, is_cancelled=None) -> None:
    """
    worker 执行：Docling -> 标准产物包 -> 注册为 RAG 包。
    """
    root = _task_root(tenant_id, task_id)
    raw_path = root / "raw" / "original.pdf"
    if not raw_path.exists():
        # 尝试找任意 original.*
        cands = list((root / "raw").glob("original.*"))
        if cands:
            raw_path = cands[0]
    if not raw_path.exists():
        update_task(tenant_id, task_id, status="failed", stage="failed", progress=100, detail="找不到任务原始文件")
        return

    update_task(
        tenant_id,
        task_id,
        status="running",
        stage="parsing",
        progress=stage_to_progress("parsing"),
        detail=None,
    )
    archive_dir = root / "archive"
    res = convert_to_md_and_json(raw_path, output_dir=archive_dir, is_cancelled=is_cancelled, tenant_id=tenant_id, kb_task_id=task_id)
    full_md = archive_dir / "full.md"
    full_json = archive_dir / "full.json"
    if res.markdown_path != full_md:
        if full_md.exists():
            full_md.unlink(missing_ok=True)
        shutil.move(str(res.markdown_path), str(full_md))
    if res.json_path != full_json:
        if full_json.exists():
            full_json.unlink(missing_ok=True)
        shutil.move(str(res.json_path), str(full_json))

    update_task(tenant_id, task_id, status="running", stage="packaging", progress=stage_to_progress("packaging"))

    kb_dir = root / "kb"
    sections_dir = kb_dir / "sections"
    sections_dir.mkdir(parents=True, exist_ok=True)
    md_text = full_md.read_text(encoding="utf-8", errors="replace")
    sections = _split_markdown_to_sections(md_text)
    section_items: list[dict[str, Any]] = []
    for idx, sec in enumerate(sections, start=1):
        sid = f"s{idx:04d}"
        fn = f"{sid}.md"
        _write_text(sections_dir / fn, sec.get("text") or "")
        section_items.append({"section_id": sid, "filename": fn, "title": sec.get("title") or sid})

    package_id = f"rp_{uuid.uuid4().hex}"
    # 2.c 约定：对外产物 manifest 至少包含 doc_id/doc_version/tenant_id/user_id/source_hash/parser_version/section_count
    # 这里没有单独的 user-doc_id 概念，使用 package_id 作为 doc_id（稳定唯一），并保留 task_id 便于追溯。
    source_hash = ""
    try:
        source_hash = hashlib.sha256(raw_path.read_bytes()).hexdigest()
    except Exception:
        source_hash = ""
    task_record = get_kb_task(tenant_id, task_id)
    pdf_title = _resolve_pdf_title(task_record, root, md_text, raw_path)
    package_name = _auto_organization_folder_name(pdf_title)

    manifest = {
        "doc_id": package_id,
        "doc_version": 1,
        "package_id": package_id,
        "task_id": task_id,
        "tenant_id": tenant_id,
        "user_id": owner_username,
        "source_filename": pdf_title,
        "source_hash": source_hash,
        "created_at": _now_iso(),
        "parser_version": res.docling_version or "docling",
        "section_count": len(section_items),
        "archive": {"full_md": "archive/full.md", "full_json": "archive/full.json"},
        "sections": section_items,
    }
    _write_json(kb_dir / "manifest.json", manifest)

    # storage_path：记录相对 uploads 的路径
    storage_rel = str(root.relative_to(Path(settings.upload_dir).resolve())).replace("\\", "/")
    _insert_rag_package(
        tenant_id,
        package_id=package_id,
        name=package_name,
        manifest=manifest,
        storage_path=storage_rel,
        owner_username=owner_username,
        created_by_task_id=task_id,
    )

    update_task(
        tenant_id,
        task_id,
        status="running",
        stage="packaging",
        progress=95,
        result_package_id=package_id,
        detail=None,
    )

    # -----------------------------------------------------------------------
    # Phase 1: Auto-organize into Private knowledge base folder
    # -----------------------------------------------------------------------
    _auto_organize_to_private_kb(
        tenant_id,
        task_id,
        owner_username,
        package_id,
        manifest,
        section_items,
        original_filename=pdf_title,
        sections_dir=sections_dir,
    )

    update_task(
        tenant_id,
        task_id,
        status="completed",
        stage="completed",
        progress=100,
        detail=None,
    )


def _auto_organization_folder_name(title: str) -> str:
    """Use uploaded PDF filename (without extension) as private KB folder name."""
    base = Path((title or "").strip() or "未命名").name.replace("..", "_")
    if "." in base:
        base = base.rsplit(".", 1)[0]
    return (base[:50] or "未命名").strip()


def _section_display_filename(section_item: dict[str, Any], used_names: set[str]) -> str:
    fallback = str(section_item.get("filename") or "s0001.md")
    title = str(section_item.get("title") or "").strip()
    if not title or title.lower() == "section":
        name = fallback
    else:
        stem = re.sub(r'[<>:"/\\|?*]+', "_", title).strip()[:80] or Path(fallback).stem
        name = stem if stem.lower().endswith(".md") else f"{stem}.md"
    if name in used_names:
        stem = Path(name).stem
        idx = 2
        while f"{stem}_{idx}.md" in used_names:
            idx += 1
        name = f"{stem}_{idx}.md"
    used_names.add(name)
    return name


def _import_section_docs_to_folder(
    tenant_id: str,
    owner_username: str,
    folder_id: str,
    private_collection_id: str,
    sections_dir: Path,
    section_items: list[dict[str, Any]],
    *,
    package_id: str,
) -> list[str]:
    """将 kb/sections 下每个小 md 注册为 user doc 并绑定到目标文件夹。"""
    from backend.services.kb_acl_store import set_resource_assignments
    from backend.services.kb_documents import _create_user_document_record
    from backend.services.kb_folders import bind_resource_to_folder

    doc_ids: list[str] = []
    used_names: set[str] = set()
    for item in section_items:
        fn = str(item.get("filename") or "").strip()
        if not fn:
            continue
        section_path = sections_dir / fn
        if not section_path.exists():
            continue
        md_bytes = section_path.read_bytes()
        display_name = _section_display_filename(item, used_names)
        doc_meta = _create_user_document_record(
            tenant_id,
            owner_username,
            filename=display_name,
            raw=md_bytes,
            initial_status="active",
        )
        doc_id = str(doc_meta["doc_id"])
        doc_root = Path(settings.upload_dir).resolve() / "kb_user_documents" / tenant_id / doc_id
        archive_dir = doc_root / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        (archive_dir / "full.md").write_bytes(md_bytes)
        mini_manifest = {
            "section_id": item.get("section_id"),
            "title": item.get("title"),
            "filename": fn,
            "parent_package_id": package_id,
            "section_count": 1,
        }
        with get_db() as db:
            db.execute(
                text(
                    "UPDATE kb_user_documents SET status='active', manifest_json=:mj WHERE tenant_id=:t AND doc_id=:d"
                ),
                {
                    "t": tenant_id,
                    "d": doc_id,
                    "mj": json.dumps(mini_manifest, ensure_ascii=False),
                },
            )
        bind_resource_to_folder(
            tenant_id,
            folder_id=folder_id,
            resource_type="doc",
            resource_id=doc_id,
        )
        set_resource_assignments(
            tenant_id,
            resource_type="doc",
            resource_id=doc_id,
            collection_ids=[private_collection_id],
        )
        doc_ids.append(doc_id)
    return doc_ids


def _auto_organize_to_private_kb(
    tenant_id: str,
    task_id: str,
    owner_username: str,
    package_id: str,
    manifest: dict[str, Any],
    section_items: list[dict[str, Any]],
    *,
    original_filename: str = "",
    sections_dir: Path | None = None,
) -> dict[str, Any] | None:
    """
    Auto-create a folder in the owner's Private kb_kind and bind the RAG package.
    Import every kb/sections/*.md as its own user document into that folder.
    Returns folder info or None on failure (non-blocking).
    """
    from backend.services.kb_collections import dynamic_private_collection_id
    from backend.services.kb_acl_store import set_private_owner, set_resource_assignments
    from backend.services.kb_folders import create_folder, bind_resource_to_folder, set_folder_collections

    try:
        private_collection_id = dynamic_private_collection_id(owner_username)
        set_private_owner(tenant_id, private_collection_id, owner_username)

        folder_title = (original_filename or "未命名").strip()
        folder_name = _auto_organization_folder_name(folder_title)
        folder_info = create_folder(
            tenant_id,
            name=folder_name,
            created_by=owner_username,
            kind="Private",
            scope={},
            owner_username=owner_username,
        )
        folder_id = folder_info["folder_id"]
        set_folder_collections(tenant_id, folder_id=folder_id, collection_ids=[private_collection_id])

        bind_resource_to_folder(
            tenant_id,
            folder_id=folder_id,
            resource_type="doc",
            resource_id=package_id,
        )
        set_resource_assignments(
            tenant_id,
            resource_type="doc",
            resource_id=package_id,
            collection_ids=[private_collection_id],
        )

        section_doc_ids: list[str] = []
        if sections_dir and sections_dir.exists() and section_items:
            section_doc_ids = _import_section_docs_to_folder(
                tenant_id,
                owner_username,
                folder_id,
                private_collection_id,
                sections_dir,
                section_items,
                package_id=package_id,
            )

        from backend.services.kb_tasks import update_task
        detail_parts = [f"folder:{folder_id}", f"section_docs:{len(section_doc_ids)}"]
        update_task(tenant_id, task_id, detail="; ".join(detail_parts))

        return {
            "folder_id": folder_id,
            "folder_name": folder_name,
            "package_id": package_id,
            "private_collection_id": private_collection_id,
            "section_doc_ids": section_doc_ids,
        }
    except Exception as e:
        # Auto-organization is best-effort; don't fail the whole task
        import logging
        logger = logging.getLogger(__name__)
        logger.warning("Auto-organization failed for task %s: %s", task_id, e)
        return None

