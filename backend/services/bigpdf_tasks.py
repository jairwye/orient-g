from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text

from backend.config import settings
from backend.database import get_db
from backend.services.docling_runner import convert_to_md_and_json
from backend.services.kb_tasks import update_task


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _root() -> Path:
    return Path(settings.upload_dir).resolve() / "kb_bigpdf_tasks"


def _task_root(tenant_id: str, task_id: str) -> Path:
    return _root() / tenant_id / task_id


def _write_text(p: Path, s: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s or "", encoding="utf-8")


def _write_json(p: Path, o: Any) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(o, ensure_ascii=False, indent=2), encoding="utf-8")


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

    update_task(tenant_id, task_id, status="running", stage="parsing", progress=stage_to_progress("parsing"))
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
    manifest = {
        "doc_id": package_id,
        "doc_version": 1,
        "package_id": package_id,
        "task_id": task_id,
        "tenant_id": tenant_id,
        "user_id": owner_username,
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
        name=f"大文档包-{package_id[-6:]}",
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
    # Extract a meaningful title from the first heading in the parsed markdown,
    # or fall back to the original filename
    pdf_title = ""
    try:
        first_line = md_text.strip().split("\n")[0]
        if first_line.startswith("#"):
            pdf_title = first_line.lstrip("#").strip()[:50]
    except Exception:
        pass
    if not pdf_title:
        pdf_title = raw_path.stem  # fallback: "original" → not great

    _auto_organize_to_private_kb(
        tenant_id,
        task_id,
        owner_username,
        package_id,
        manifest,
        section_items,
        original_filename=pdf_title,
        full_md_path=full_md,
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
    """Generate folder name from original PDF filename, truncated."""
    base = (title or "").strip() or "未命名"
    # Remove file extension for cleaner display
    if "." in base:
        base = base.rsplit(".", 1)[0]
    truncated = base[:50]
    return f"大PDF-{truncated}"


def _auto_organize_to_private_kb(
    tenant_id: str,
    task_id: str,
    owner_username: str,
    package_id: str,
    manifest: dict[str, Any],
    section_items: list[dict[str, Any]],
    *,
    original_filename: str = "",
    full_md_path: Path | None = None,
) -> dict[str, Any] | None:
    """
    Auto-create a folder in the owner's Private kb_kind and bind the RAG package.
    Also creates a kb_user_documents record from the full markdown so the folder
    shows actual content in the knowledge base UI.
    Returns folder info or None on failure (non-blocking).
    """
    from backend.services.kb_collections import dynamic_private_collection_id
    from backend.services.kb_acl_store import set_private_owner, set_resource_assignments
    from backend.services.kb_folders import create_folder, bind_resource_to_folder, set_folder_collections
    from backend.services.kb_documents import _create_user_document_record

    try:
        private_collection_id = dynamic_private_collection_id(owner_username)
        set_private_owner(tenant_id, private_collection_id, owner_username)

        # Folder name: use original PDF filename, trimmed
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

        # Bind RAG package to folder
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

        # Create a kb_user_documents record for the full markdown content
        # so the folder shows actual content in the knowledge base UI
        user_doc_id = ""
        if full_md_path and full_md_path.exists():
            try:
                md_text = full_md_path.read_text(encoding="utf-8", errors="replace")
                md_bytes = md_text.encode("utf-8")
                safe_name = Path(folder_title).name.replace("..", "_") or "parsed"
                if not safe_name.endswith(".md"):
                    safe_name = f"{safe_name}.md"
                doc_meta = _create_user_document_record(
                    tenant_id,
                    owner_username,
                    filename=safe_name,
                    raw=md_bytes,
                    initial_status="active",  # already parsed
                )
                user_doc_id = str(doc_meta["doc_id"])
                # Bind the user document to this folder
                bind_resource_to_folder(
                    tenant_id,
                    folder_id=folder_id,
                    resource_type="doc",
                    resource_id=user_doc_id,
                )
                set_resource_assignments(
                    tenant_id,
                    resource_type="doc",
                    resource_id=user_doc_id,
                    collection_ids=[private_collection_id],
                )
                # Write the markdown content to the user document's archive
                from pathlib import Path as _Path
                doc_root = _Path(settings.upload_dir).resolve() / "kb_user_documents" / tenant_id / user_doc_id
                archive_dir = doc_root / "archive"
                archive_dir.mkdir(parents=True, exist_ok=True)
                (archive_dir / "full.md").write_text(md_text, encoding="utf-8")
                # Update status to packaged/active
                from backend.database import get_db
                from sqlalchemy import text
                with get_db() as db:
                    db.execute(
                        text("UPDATE kb_user_documents SET status='active', manifest_json=:mj WHERE tenant_id=:t AND doc_id=:d"),
                        {"t": tenant_id, "d": user_doc_id, "mj": json.dumps(manifest, ensure_ascii=False)},
                    )
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning("Failed to create user doc for bigpdf task %s: %s", task_id, e)

        # Update task with folder info
        from backend.services.kb_tasks import update_task
        detail_parts = [f"folder:{folder_id}"]
        if user_doc_id:
            detail_parts.append(f"user_doc:{user_doc_id}")
        update_task(tenant_id, task_id, detail="; ".join(detail_parts))

        return {
            "folder_id": folder_id,
            "folder_name": folder_name,
            "package_id": package_id,
            "private_collection_id": private_collection_id,
        }
    except Exception as e:
        # Auto-organization is best-effort; don't fail the whole task
        import logging
        logger = logging.getLogger(__name__)
        logger.warning("Auto-organization failed for task %s: %s", task_id, e)
        return None

