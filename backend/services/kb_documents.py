"""
用户上传文档：存储、分块、私人库 assignment、共享到多类知识库。
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import bindparam, text

from backend.config import settings
from backend.database import get_db
from backend.services.docling_runner import convert_to_md_and_json
from backend.services._kb_helpers import now_iso as _now_iso, write_text as _write_text, write_json as _write_json
from backend.services.kb_acl_store import (
    get_doc_collection_ids,
    set_private_owner,
    set_resource_assignments,
    set_resource_owner,
)
from backend.services.kb_collections import dynamic_private_collection_id, resolve_share_collection_ids
from backend.services.kb_folders import bind_resource_to_folder, ensure_private_folder
from backend.services.task_queue import Priority, submit, TASK_EMBED_AND_INDEX_REFRESH
from backend.services.kb_vector_index import index_uploaded_document_task
from backend.services.kb_doc_lifecycle import transition_document_status, validate_manifest
from backend.services.kb_vector_store import vector_enabled


def _kb_docs_root() -> Path:
    return Path(settings.upload_dir).resolve() / "kb_user_documents"


def _doc_root(tenant_id: str, doc_id: str) -> Path:
    return _kb_docs_root() / tenant_id / doc_id


def _split_markdown_to_sections(md: str) -> list[dict[str, Any]]:
    """
    最小分段策略：按一级/二级标题切分，保证 section 数量可控且稳定。
    后续可切换为基于 Docling JSON 的结构化分段，但 section_id/manifest 映射不变。
    """
    text = (md or "").replace("\r\n", "\n")
    lines = text.split("\n")
    sections: list[dict[str, Any]] = []
    buf: list[str] = []
    title = "Section 1"

    def flush():
        nonlocal buf, title
        body = "\n".join(buf).strip()
        if body:
            sections.append({"title": title, "text": body})
        buf = []

    for ln in lines:
        if re.match(r"^#{1,2}\s+\S", ln.strip()):
            flush()
            title = ln.lstrip("#").strip()[:200] or "Untitled"
            buf.append(ln)
        else:
            buf.append(ln)
    flush()

    if not sections:
        sections = [{"title": "Section 1", "text": text.strip() or "（空文档）"}]
    return sections[:200]


def _extract_text(filename: str, raw: bytes) -> str:
    fn = (filename or "").lower()
    if fn.endswith((".txt", ".md", ".csv", ".json", ".log")):
        for enc in ("utf-8", "utf-8-sig", "gbk"):
            try:
                return raw.decode(enc)
            except Exception:
                continue
        return raw.decode("utf-8", errors="replace")
    if fn.endswith(".html") or fn.endswith(".htm"):
        try:
            s = raw.decode("utf-8", errors="replace")
        except Exception:
            s = raw.decode("gbk", errors="replace")
        return re.sub(r"<[^>]+>", " ", s)
    try:
        return raw.decode("utf-8", errors="replace")
    except Exception:
        return "[无法解码为文本，请上传 .txt / .md / .html]"


def _chunk_by_sections(
    sections: list[dict[str, Any]],
    *,
    max_section_chars: int = 15000,
    max_split_chars: int = 10000,
) -> list[dict[str, Any]]:
    """
    按 section 边界整块切分，保留文档结构。
    
    策略：
    - 一个 section ≤ max_section_chars → 一个完整 chunk（含标题）
    - 一个 section > max_section_chars → 按段落边界二次切分（max_split_chars）
    
    返回: [{chunk_id, chunk_seq_no, text}] — text 已包含 "## {title}\n" 前缀
    """
    chunks: list[dict[str, Any]] = []
    seq = 0
    text = ""  # 防止空 sections 列表时 NameError

    for sec in sections:
        title = str(sec.get("title") or "")
        text = str(sec.get("text") or "").strip()
        sid = str(sec.get("section_id") or f"s{seq+1:04d}")

        if not text:
            continue

        # 拼接标题 + 正文
        full = f"## {title}\n{text}" if title else text

        if len(full) <= max_section_chars:
            seq += 1
            chunks.append({
                "chunk_id": sid,
                "chunk_seq_no": seq,
                "text": full,
            })
        else:
            # 大 section：按段落边界切
            paragraphs = re.split(r"\n\s*\n+", text)
            buf = f"## {title}\n" if title else ""
            for para in paragraphs:
                para = para.strip()
                if not para:
                    continue
                if len(buf) + len(para) + 2 <= max_split_chars:
                    buf = f"{buf}\n\n{para}" if buf.strip() else para
                else:
                    if buf.strip():
                        seq += 1
                        chunks.append({
                            "chunk_id": f"{sid}_p{len([c for c in chunks if c['chunk_id'].startswith(sid)]) + 1}",
                            "chunk_seq_no": seq,
                            "text": buf,
                        })
                    buf = f"## {title}\n{para}" if title else para
            if buf.strip():
                seq += 1
                chunks.append({
                    "chunk_id": f"{sid}_p{len([c for c in chunks if c['chunk_id'].startswith(sid)]) + 1}",
                    "chunk_seq_no": seq,
                    "text": buf,
                })

    if not chunks:
        chunks.append({"chunk_id": "s0001", "chunk_seq_no": 1, "text": text or "(空文档)"})

    return chunks


def _create_user_document_record(
    tenant_id: str,
    owner_username: str,
    *,
    filename: str,
    raw: bytes,
    initial_status: str = "uploaded",
) -> dict[str, Any]:
    doc_id = f"ud_{uuid.uuid4().hex}"
    safe_name = Path(filename or "upload").name.replace("..", "_")
    root = _doc_root(tenant_id, doc_id)
    raw_dir = root / "raw"
    archive_dir = root / "archive"
    kb_dir = root / "kb"
    sections_dir = kb_dir / "sections"
    for d in (raw_dir, archive_dir, sections_dir):
        d.mkdir(parents=True, exist_ok=True)

    # 2.c 优先约定 raw/original.pdf；若不是 pdf，仍保留扩展名，避免误导。
    ext = Path(safe_name).suffix.lower()
    raw_name = "original.pdf" if ext == ".pdf" else f"original{ext or ''}".rstrip(".")
    raw_path = raw_dir / raw_name
    raw_path.write_bytes(raw)
    source_hash = hashlib.sha256(raw).hexdigest()

    storage_rel = f"kb_user_documents/{tenant_id}/{doc_id}/raw/{raw_name}"

    title = Path(safe_name).stem or doc_id
    pcid = dynamic_private_collection_id(owner_username)

    with get_db() as db:
        db.execute(
            text(
                """
                INSERT INTO kb_user_documents
                    (doc_id, tenant_id, owner_username, title, original_filename, storage_path, mime, size_bytes, status, doc_version, source_hash, updated_at)
                VALUES (:id, :tid, :owner, :title, :ofn, :sp, :mime, :sz, :status, 'v1', :h, CURRENT_TIMESTAMP)
                """
            ),
            {
                "id": doc_id,
                "tid": tenant_id,
                "owner": owner_username,
                "title": title,
                "ofn": safe_name,
                "sp": storage_rel,
                "mime": "application/octet-stream",
                "sz": len(raw),
                "status": str(initial_status or "uploaded"),
                "h": source_hash,
            },
        )

    set_private_owner(tenant_id, pcid, owner_username)
    set_resource_assignments(tenant_id, resource_type="doc", resource_id=doc_id, collection_ids=[pcid])
    set_resource_owner(tenant_id, resource_type="doc", resource_id=doc_id, owner_username=owner_username)
    # folder-first：所有文档必须归入一个 folder（默认：用户私有 folder）
    try:
        fid = ensure_private_folder(tenant_id, username=owner_username)
        bind_resource_to_folder(tenant_id, folder_id=fid, resource_type="doc", resource_id=doc_id)
    except Exception:
        # 不阻塞上传；若 DB 未迁移/无表则忽略，由回填脚本修复
        pass

    return {
        "doc_id": doc_id,
        "title": title,
        "private_collection_id": pcid,
        "safe_name": safe_name,
        "raw_path": raw_path,
        "source_hash": source_hash,
        "storage_path": storage_rel,
    }


def _parse_and_package_document(
    tenant_id: str,
    owner_username: str,
    *,
    doc_id: str,
    title: str,
    safe_name: str,
    raw_path: Path,
    source_hash: str,
    private_collection_id: str,
    is_cancelled: callable | None = None,
    status_before_parse: str = "uploaded",
) -> dict[str, Any]:
    root = _doc_root(tenant_id, doc_id)
    archive_dir = root / "archive"
    kb_dir = root / "kb"
    sections_dir = kb_dir / "sections"
    for d in (archive_dir, sections_dir):
        d.mkdir(parents=True, exist_ok=True)

    ext = Path(safe_name).suffix.lower()
    text_like_exts = {".txt", ".md", ".csv", ".json", ".log", ".html", ".htm"}
    parser_version = "docling"
    try:
        full_md = archive_dir / "full.md"
        full_json = archive_dir / "full.json"
        # 文本类小文件不走 Docling，避免额外模型依赖/上游压力。
        if ext in text_like_exts:
            txt = _extract_text(safe_name, raw_path.read_bytes())
            full_md.write_text(txt or "", encoding="utf-8")
            full_json.write_text(
                json.dumps(
                    {
                        "kind": "plain_text",
                        "filename": safe_name,
                        "length": len(txt or ""),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            parser_version = "builtin-text"
        else:
            res = convert_to_md_and_json(raw_path, output_dir=archive_dir, is_cancelled=is_cancelled)
            # 统一命名
            if res.markdown_path != full_md:
                if full_md.exists():
                    full_md.unlink(missing_ok=True)
                shutil.move(str(res.markdown_path), str(full_md))
            if res.json_path != full_json:
                if full_json.exists():
                    full_json.unlink(missing_ok=True)
                shutil.move(str(res.json_path), str(full_json))
            parser_version = res.docling_version or "docling"

        transition_document_status(
            tenant_id,
            doc_id,
            "parsed",
            from_status=status_before_parse,
            parser_version=parser_version,
            source_hash=source_hash,
        )
    except Exception as e:
        transition_document_status(
            tenant_id,
            doc_id,
            "failed",
            from_status=status_before_parse,
            last_error=str(e),
            source_hash=source_hash,
            skip_validation=True,
        )
        raise

    # 打包分段 -> kb/sections/*.md + manifest.json
    md_text = (archive_dir / "full.md").read_text(encoding="utf-8", errors="replace")
    sections = _split_markdown_to_sections(md_text)
    section_items: list[dict[str, Any]] = []
    for idx, sec in enumerate(sections, start=1):
        sid = f"s{idx:04d}"
        sec["section_id"] = sid  # enrich for structured chunking
        fn = f"{sid}.md"
        _write_text(sections_dir / fn, sec["text"])
        section_items.append({"section_id": sid, "filename": fn, "title": sec.get("title") or sid})

    manifest = {
        "doc_id": doc_id,
        "doc_version": "v1",
        "tenant_id": tenant_id,
        "user_id": owner_username,
        "classification": "internal",
        "created_at": _now_iso(),
        "source_hash": source_hash,
        "parser_version": parser_version,
        "section_count": len(section_items),
        "original_filename": safe_name,
        "raw_path": str(raw_path.relative_to(Path(settings.upload_dir).resolve())).replace("\\", "/"),
        "archive": {"full_md": "archive/full.md", "full_json": "archive/full.json"},
        "sections": section_items,
    }
    _write_json(kb_dir / "manifest.json", manifest)
    missing = validate_manifest(manifest)
    if missing:
        raise RuntimeError(f"manifest missing keys: {missing}")

    transition_document_status(
        tenant_id,
        doc_id,
        "packaged",
        from_status="parsed",
        manifest_json=json.dumps(manifest, ensure_ascii=False),
    )

    # assigned/active：当前 internal 闭环下，打包完成即视为已归属可用
    transition_document_status(tenant_id, doc_id, "active", from_status="packaged")

    # chunks：按 section 边界整块切分（保留文档结构，替代旧 1200 字符等距切）
    struct_chunks = _chunk_by_sections(sections)
    with get_db() as db:
        for ch in struct_chunks:
            db.execute(
                text(
                    """
                    INSERT INTO kb_user_document_chunks (doc_id, chunk_id, chunk_seq_no, chunk_text)
                    VALUES (:did, :cid, :seq, :txt)
                    ON CONFLICT (doc_id, chunk_id) DO NOTHING
                    """
                ),
                {"did": doc_id, "cid": f"{doc_id}_{ch['chunk_id']}", "seq": ch["chunk_seq_no"], "txt": ch["text"][:65000]},
            )

    # 向量索引：后台异步（不阻塞上传）；默认关闭（keyword-only）
    if vector_enabled():
        try:
            submit(
                Priority.LOW,
                index_uploaded_document_task,
                tenant_id,
                doc_id,
                task_id=f"index_{doc_id}",
                task_type=TASK_EMBED_AND_INDEX_REFRESH,
            )
        except Exception:
            pass

    return {
        "doc_id": doc_id,
        "title": title,
        "private_collection_id": private_collection_id,
        "chunk_count": len(struct_chunks),
        "status": "active",
    }


def mark_document_failed(tenant_id: str, doc_id: str, detail: str) -> None:
    transition_document_status(
        tenant_id,
        doc_id,
        "failed",
        last_error=str(detail or ""),
        skip_validation=True,
    )


def mark_document_status(tenant_id: str, doc_id: str, status: str, detail: str | None = None) -> None:
    transition_document_status(
        tenant_id,
        doc_id,
        str(status or "queued"),
        last_error=detail,
        skip_validation=True,
    )


def recover_pending_document_tasks(tenant_id: str, *, limit: int = 200) -> dict[str, int]:
    from backend.services.task_queue import enqueue_user_doc_task

    rows = []
    with get_db() as db:
        rows = db.execute(
            text(
                """
                SELECT doc_id, owner_username
                FROM kb_user_documents
                WHERE tenant_id=:t AND status IN ('queued', 'parsing')
                ORDER BY updated_at ASC
                LIMIT :lim
                """
            ),
            {"t": tenant_id, "lim": max(1, int(limit))},
        ).fetchall()
    accepted = 0
    rejected = 0
    for r in rows:
        did = str(r[0] or "").strip()
        owner = str(r[1] or "").strip()
        if not did or not owner:
            continue
        ok, _ = enqueue_user_doc_task(tenant_id, owner, did)
        if ok:
            accepted += 1
        else:
            rejected += 1
    return {"total": len(rows), "accepted": accepted, "rejected": rejected}


def upload_user_document(
    tenant_id: str,
    owner_username: str,
    *,
    filename: str,
    raw: bytes,
) -> dict[str, Any]:
    meta = _create_user_document_record(
        tenant_id,
        owner_username,
        filename=filename,
        raw=raw,
        initial_status="uploaded",
    )
    return _parse_and_package_document(
        tenant_id,
        owner_username,
        doc_id=str(meta["doc_id"]),
        title=str(meta["title"]),
        safe_name=str(meta["safe_name"]),
        raw_path=Path(meta["raw_path"]),
        source_hash=str(meta["source_hash"]),
        private_collection_id=str(meta["private_collection_id"]),
    )


def upload_user_document_async(
    tenant_id: str,
    owner_username: str,
    *,
    filename: str,
    raw: bytes,
) -> dict[str, Any]:
    meta = _create_user_document_record(
        tenant_id,
        owner_username,
        filename=filename,
        raw=raw,
        initial_status="queued",
    )
    return {
        "doc_id": str(meta["doc_id"]),
        "title": str(meta["title"]),
        "private_collection_id": str(meta["private_collection_id"]),
        "chunk_count": 0,
        "status": "queued",
    }


def process_uploaded_document_task(tenant_id: str, doc_id: str, is_cancelled=None) -> None:
    with get_db() as db:
        row = db.execute(
            text(
                """
                SELECT owner_username, title, original_filename, storage_path, source_hash
                FROM kb_user_documents
                WHERE tenant_id=:t AND doc_id=:d
                """
            ),
            {"t": tenant_id, "d": doc_id},
        ).fetchone()
        if not row:
            raise RuntimeError(f"document not found: {doc_id}")
        transition_document_status(tenant_id, doc_id, "parsing", from_status="queued")
    owner_username = str(row[0] or "")
    title = str(row[1] or doc_id)
    safe_name = str(row[2] or "upload")
    storage_path = str(row[3] or "").strip()
    source_hash = str(row[4] or "").strip()
    if not storage_path:
        raise RuntimeError(f"missing storage_path for {doc_id}")
    raw_path = Path(settings.upload_dir).resolve() / storage_path
    if not raw_path.exists():
        raise RuntimeError(f"raw file not found: {raw_path}")
    if not source_hash:
        source_hash = hashlib.sha256(raw_path.read_bytes()).hexdigest()
    pcid = dynamic_private_collection_id(owner_username)
    _parse_and_package_document(
        tenant_id,
        owner_username,
        doc_id=doc_id,
        title=title,
        safe_name=safe_name,
        raw_path=raw_path,
        source_hash=source_hash,
        private_collection_id=pcid,
        status_before_parse="parsing",
    )


def list_my_documents(tenant_id: str, owner_username: str) -> list[dict[str, Any]]:
    with get_db() as db:
        rows = db.execute(
            text(
                """
                SELECT doc_id, title, original_filename, size_bytes, status, created_at, last_error
                FROM kb_user_documents
                WHERE tenant_id = :tid AND owner_username = :owner
                ORDER BY created_at DESC
                """
            ),
            {"tid": tenant_id, "owner": owner_username},
        ).fetchall()
    doc_ids = [str(r[0]) for r in rows if r and r[0]]
    folder_by_doc: dict[str, list[str]] = {}
    if doc_ids:
        with get_db() as db:
            placeholders = ", ".join([f":d{i}" for i in range(len(doc_ids))])
            params: dict[str, Any] = {"tid": tenant_id}
            for i, did in enumerate(doc_ids):
                params[f"d{i}"] = did
            fr_rows = db.execute(
                text(
                    f"""
                    SELECT resource_id, folder_id
                    FROM kb_folder_resources
                    WHERE tenant_id = :tid AND resource_type = 'doc' AND resource_id IN ({placeholders})
                    """
                ),
                params,
            ).fetchall()
        for fr in fr_rows:
            rid = str(fr[0] or "")
            fid = str(fr[1] or "")
            if rid and fid:
                folder_by_doc.setdefault(rid, []).append(fid)
    out = []
    for r in rows:
        did = str(r[0])
        cids = get_doc_collection_ids(tenant_id, did)
        out.append(
            {
                "doc_id": did,
                "title": str(r[1] or ""),
                "original_filename": str(r[2] or ""),
                "size_bytes": int(r[3] or 0),
                "status": str(r[4] or ""),
                "created_at": r[5].isoformat() if r[5] else None,
                "last_error": str(r[6] or "") if r[6] else None,
                "collection_ids": cids,
                "folder_ids": folder_by_doc.get(did, []),
            }
        )
    return out


MY_DOC_UPLOAD_MAX_BYTES = 20 * 1024 * 1024


def normalize_source_hash(value: str | None) -> str:
    return str(value or "").strip().lower()


def compute_source_hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def find_doc_id_by_source_hash_in_folder_subtree(
    tenant_id: str,
    folder_id: str,
    source_hash: str,
) -> str | None:
    """在 folder 子树内按 source_hash 查找已有文档（增量上传跳过）。"""
    from backend.services.kb_folders import collect_subtree_doc_ids

    h = normalize_source_hash(source_hash)
    if not h:
        return None
    fid = (folder_id or "").strip()
    if not fid:
        return None
    doc_ids = collect_subtree_doc_ids(tenant_id, fid)
    if not doc_ids:
        return None
    tid = (tenant_id or "").strip() or "tenant1"
    with get_db() as db:
        rows = db.execute(
            text(
                """
                SELECT doc_id, source_hash
                FROM kb_user_documents
                WHERE tenant_id=:t AND doc_id IN :ids AND source_hash IS NOT NULL
                """
            ).bindparams(bindparam("ids", expanding=True)),
            {"t": tid, "ids": doc_ids},
        ).fetchall()
    for row in rows:
        if normalize_source_hash(str(row[1] or "")) == h:
            return str(row[0] or "").strip() or None
    return None


def map_source_hashes_in_folder_subtree(
    tenant_id: str,
    folder_id: str,
    source_hashes: list[str],
) -> dict[str, str]:
    """批量：返回子树内已存在的 source_hash -> doc_id（小写 hash 键）。"""
    from backend.services.kb_folders import collect_subtree_doc_ids

    want = {normalize_source_hash(h) for h in (source_hashes or []) if normalize_source_hash(h)}
    if not want:
        return {}
    fid = (folder_id or "").strip()
    if not fid:
        return {}
    doc_ids = collect_subtree_doc_ids(tenant_id, fid)
    if not doc_ids:
        return {}
    tid = (tenant_id or "").strip() or "tenant1"
    out: dict[str, str] = {}
    with get_db() as db:
        rows = db.execute(
            text(
                """
                SELECT doc_id, source_hash
                FROM kb_user_documents
                WHERE tenant_id=:t AND doc_id IN :ids AND source_hash IS NOT NULL
                """
            ).bindparams(bindparam("ids", expanding=True)),
            {"t": tid, "ids": doc_ids},
        ).fetchall()
    for row in rows:
        h = normalize_source_hash(str(row[1] or ""))
        did = str(row[0] or "").strip()
        if h in want and did and h not in out:
            out[h] = did
    return out


def get_document_owner(tenant_id: str, doc_id: str) -> str | None:
    with get_db() as db:
        row = db.execute(
            text("SELECT owner_username FROM kb_user_documents WHERE tenant_id=:t AND doc_id=:d"),
            {"t": tenant_id, "d": doc_id},
        ).fetchone()
    return str(row[0]) if row else None


def delete_user_document(tenant_id: str, owner_username: str, doc_id: str) -> bool:
    if get_document_owner(tenant_id, doc_id) != owner_username:
        return False
    with get_db() as db:
        db.execute(text("DELETE FROM kb_user_document_chunks WHERE doc_id=:d"), {"d": doc_id})
        db.execute(text("DELETE FROM kb_user_documents WHERE tenant_id=:t AND doc_id=:d"), {"t": tenant_id, "d": doc_id})
        db.execute(text("DELETE FROM kb_document_shares WHERE doc_id=:d"), {"d": doc_id})
        try:
            db.execute(
                text(
                    """
                    DELETE FROM kb_folder_resources
                    WHERE tenant_id=:t AND resource_type='doc' AND resource_id=:d
                    """
                ),
                {"t": tenant_id, "d": doc_id},
            )
        except Exception:
            pass
    set_resource_assignments(tenant_id, resource_type="doc", resource_id=doc_id, collection_ids=[])
    # 清理磁盘
    try:
        folder = _doc_root(tenant_id, doc_id)
        if folder.exists():
            shutil.rmtree(folder, ignore_errors=True)
    except Exception:
        pass
    return True


def load_user_docs_as_fixture_documents(tenant_id: str, doc_ids: set[str]) -> list[dict[str, Any]]:
    want = {str(x) for x in doc_ids if str(x).startswith("ud_")}
    if not want:
        return []
    dids: list[str] = []
    title_map: dict[str, str] = {}
    with get_db() as db:
        for did in sorted(want):
            row = db.execute(
                text("SELECT doc_id, title FROM kb_user_documents WHERE tenant_id=:t AND doc_id=:d"),
                {"t": tenant_id, "d": did},
            ).fetchone()
            if row:
                dids.append(str(row[0]))
                title_map[str(row[0])] = str(row[1] or "")
    if not dids:
        return []
    ch_rows: list[Any] = []
    with get_db() as db:
        for did in dids:
            rows = db.execute(
                text(
                    """
                    SELECT doc_id, chunk_id, chunk_seq_no, chunk_text
                    FROM kb_user_document_chunks
                    WHERE doc_id = :did
                    ORDER BY chunk_seq_no
                    """
                ),
                {"did": did},
            ).fetchall()
            ch_rows.extend(rows)
    by_doc: dict[str, list[dict[str, Any]]] = {}
    for r in ch_rows:
        did = str(r[0])
        by_doc.setdefault(did, []).append(
            {"chunk_id": str(r[1]), "chunk_seq_no": int(r[2] or 0), "text": str(r[3] or "")}
        )
    out: list[dict[str, Any]] = []
    for did in dids:
        chunks = by_doc.get(did, [])
        out.append(
            {
                "doc_id": did,
                "tenant_id": tenant_id,
                "title": title_map.get(did, did),
                "collection_ids": [],
                "sections": [
                    {
                        "section_id": f"{did}_s1",
                        "keywords": [],
                        "text": "",
                        "chunks": chunks,
                    }
                ],
            }
        )
    return out


def list_all_uploaded_doc_ids(tenant_id: str) -> list[str]:
    with get_db() as db:
        rows = db.execute(
            text("SELECT doc_id FROM kb_user_documents WHERE tenant_id=:t"),
            {"t": tenant_id},
        ).fetchall()
    return [str(r[0]) for r in rows]


def list_uploaded_doc_ids_by_owner(tenant_id: str, owner_username: str) -> list[str]:
    ou = (owner_username or "").strip()
    if not ou:
        return []
    with get_db() as db:
        rows = db.execute(
            text("SELECT doc_id FROM kb_user_documents WHERE tenant_id=:t AND owner_username=:u"),
            {"t": tenant_id, "u": ou},
        ).fetchall()
    return [str(r[0]) for r in rows]


def list_chunk_ids_for_doc(tenant_id: str, doc_id: str) -> list[str]:
    with get_db() as db:
        rows = db.execute(
            text("SELECT chunk_id FROM kb_user_document_chunks WHERE doc_id=:d ORDER BY chunk_seq_no"),
            {"d": doc_id},
        ).fetchall()
    return [str(r[0]) for r in rows]


def share_document(
    tenant_id: str,
    owner_username: str,
    doc_id: str,
    fixtures: dict[str, Any],
    *,
    kb_kind: str,
    department_ids: list[str] | None = None,
    project_ids: list[str] | None = None,
    company_public: bool = False,
) -> dict[str, Any]:
    if get_document_owner(tenant_id, doc_id) != owner_username:
        raise PermissionError("not owner")
    department_ids = department_ids or []
    project_ids = project_ids or []
    extra: list[str] = []
    if company_public:
        extra.extend(
            resolve_share_collection_ids(
                fixtures, tenant_id, kb_kind="CompanyPublic", department_ids=[], project_ids=[], company_public=True
            )
        )
    extra.extend(
        resolve_share_collection_ids(
            fixtures,
            tenant_id,
            kb_kind=kb_kind,
            department_ids=department_ids,
            project_ids=project_ids,
            company_public=False,
        )
    )
    if not extra:
        return {"ok": False, "detail": "no target collections", "collection_ids": []}

    existing = set(get_doc_collection_ids(tenant_id, doc_id))
    merged = sorted(existing.union(extra))
    set_resource_assignments(tenant_id, resource_type="doc", resource_id=doc_id, collection_ids=merged)

    with get_db() as db:
        db.execute(
            text(
                """
                INSERT INTO kb_document_shares (doc_id, shared_by, target_kind, target_json)
                VALUES (:d, :u, :k, :j)
                """
            ),
            {
                "d": doc_id,
                "u": owner_username,
                "k": kb_kind,
                "j": json.dumps(
                    {"department_ids": department_ids, "project_ids": project_ids, "company_public": company_public},
                    ensure_ascii=False,
                ),
            },
        )

    return {"ok": True, "collection_ids": merged}


def get_doc_share_targets(doc_id: str) -> list[dict[str, Any]]:
    """
    返回该文档所有 share 记录（按时间倒序）。
    表 kb_document_shares 为历史记录表，允许同一 doc 多次共享到不同目标。
    """
    did = (doc_id or "").strip()
    if not did:
        return []
    with get_db() as db:
        rows = db.execute(
            text(
                """
                SELECT target_kind, target_json, shared_by, created_at
                FROM kb_document_shares
                WHERE doc_id = :d
                ORDER BY created_at DESC, id DESC
                """
            ),
            {"d": did},
        ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        kind = str(r[0] or "").strip()
        raw = str(r[1] or "").strip()
        try:
            j = json.loads(raw) if raw else {}
        except Exception:
            j = {}
        if not isinstance(j, dict):
            j = {}
        out.append(
            {
                "target_kind": kind,
                "target": j,
                "shared_by": str(r[2] or "").strip(),
                "created_at": str(r[3] or "").strip(),
            }
        )
    return out


SPECIAL_ADMIN_COLLECTION_IDS = frozenset(
    {
        "c_multi_dept_public_1",
        "c_multi_dept_lead_1",
        "c_multi_project_public_1",
        "c_multi_project_lead_1",
        "c_company_public_1",
        "c_management_public_1",
    }
)


def list_docs_touching_collections(tenant_id: str, trigger_collections: set[str]) -> list[dict[str, Any]]:
    if not trigger_collections:
        return []
    with get_db() as db:
        rows = db.execute(
            text(
                """
                SELECT resource_id, collection_id
                FROM kb_resource_collection_assignments
                WHERE tenant_id = :t AND resource_type = 'doc'
                """
            ),
            {"t": tenant_id},
        ).fetchall()
    by_doc: dict[str, set[str]] = {}
    for r in rows:
        rid, cid = str(r[0] or ""), str(r[1] or "")
        if not rid or not cid:
            continue
        by_doc.setdefault(rid, set()).add(cid)
    out: list[dict[str, Any]] = []
    for rid, cids in sorted(by_doc.items()):
        if cids & trigger_collections:
            out.append({"doc_id": rid, "collection_ids": sorted(cids)})
    return out


def get_special_doc_acl(tenant_id: str, resource_id: str) -> dict[str, Any]:
    with get_db() as db:
        row = db.execute(
            text(
                """
                SELECT acl_json FROM kb_special_doc_acl
                WHERE tenant_id=:t AND resource_type='doc' AND resource_id=:r
                """
            ),
            {"t": tenant_id, "r": resource_id},
        ).fetchone()
    if not row or not row[0]:
        # 特殊文档权限：默认不放开（Multi* 的可读范围由 share_scope 控制；CompanyPublic 由 collection 自身规则控制）
        return {}
    try:
        o = json.loads(str(row[0]))
        return o if isinstance(o, dict) else {}
    except Exception:
        return {}


def set_special_doc_acl(tenant_id: str, resource_id: str, acl: dict[str, Any]) -> None:
    with get_db() as db:
        db.execute(
            text(
                """
                INSERT INTO kb_special_doc_acl (tenant_id, resource_type, resource_id, acl_json)
                VALUES (:t, 'doc', :r, :j)
                ON CONFLICT (tenant_id, resource_type, resource_id) DO UPDATE
                SET acl_json = EXCLUDED.acl_json
                """
            ),
            {"t": tenant_id, "r": resource_id, "j": json.dumps(acl, ensure_ascii=False)},
        )


def merge_special_doc_acl(tenant_id: str, resource_id: str, updates: dict[str, Any]) -> None:
    cur = get_special_doc_acl(tenant_id, resource_id)
    merged = {**cur, **updates}
    set_special_doc_acl(tenant_id, resource_id, merged)


def list_doc_ids_with_management_acl(tenant_id: str) -> list[str]:
    tid = (tenant_id or "").strip() or "tenant1"
    with get_db() as db:
        rows = db.execute(
            text(
                """
                SELECT resource_id, acl_json FROM kb_special_doc_acl
                WHERE tenant_id=:t AND resource_type='doc'
                """
            ),
            {"t": tid},
        ).fetchall()
    out: list[str] = []
    for r in rows:
        did = str(r[0] or "").strip()
        if not did:
            continue
        try:
            acl = json.loads(str(r[1] or "{}"))
        except Exception:
            acl = {}
        if isinstance(acl, dict) and acl.get("allow_management"):
            out.append(did)
    return out


def add_management_doc_share(doc_id: str, shared_by: str) -> None:
    did = (doc_id or "").strip()
    un = (shared_by or "").strip()
    if not did or not un:
        return
    with get_db() as db:
        db.execute(
            text(
                """
                INSERT INTO kb_document_shares (doc_id, shared_by, target_kind, target_json)
                VALUES (:d, :u, 'ManagementPublic', :j)
                """
            ),
            {"d": did, "u": un, "j": json.dumps({}, ensure_ascii=False)},
        )


def revoke_management_doc_share(doc_id: str) -> None:
    did = (doc_id or "").strip()
    if not did:
        return
    with get_db() as db:
        db.execute(
            text("DELETE FROM kb_document_shares WHERE doc_id=:d AND target_kind='ManagementPublic'"),
            {"d": did},
        )


def clear_management_special_acl(tenant_id: str, resource_id: str) -> None:
    tid = (tenant_id or "").strip() or "tenant1"
    rid = (resource_id or "").strip()
    if not rid:
        return
    acl = get_special_doc_acl(tid, rid)
    if not acl.get("allow_management"):
        return
    new_acl = {k: v for k, v in acl.items() if k != "allow_management"}
    if new_acl:
        set_special_doc_acl(tid, rid, new_acl)
    else:
        with get_db() as db:
            db.execute(
                text(
                    """
                    DELETE FROM kb_special_doc_acl
                    WHERE tenant_id=:t AND resource_type='doc' AND resource_id=:r
                    """
                ),
                {"t": tid, "r": rid},
            )


_UNFILED_SPECIAL_FOLDER_ID = "__unfiled__"

_SPECIAL_SHARE_TARGET_KINDS = frozenset(
    {
        "CompanyPublic",
        "ManagementPublic",
        "MultiDeptPublic",
        "MultiDeptLead",
        "MultiProjectPublic",
        "MultiProjectLead",
        "DeptPublic",
        "DeptLead",
        "ProjectPublic",
        "ProjectLead",
    }
)


def _folder_depth(folder: dict[str, Any], by_id: dict[str, dict[str, Any]]) -> int:
    depth = 0
    cur = str(folder.get("parent_folder_id") or "").strip()
    seen: set[str] = set()
    while cur and cur not in seen:
        seen.add(cur)
        depth += 1
        parent = by_id.get(cur)
        cur = str(parent.get("parent_folder_id") or "").strip() if parent else ""
    return depth


def _folder_share_scope_from_meta(
    folder: dict[str, Any],
    tenant_id: str,
    overlap_sorted: list[str],
    col_by_id: dict[str, dict[str, Any]],
    fixtures: dict[str, Any],
) -> dict[str, list[str]]:
    from backend.services.kb_acl_store import get_collection_scope
    from backend.services.kb_collections import share_kinds_for_collection_ids

    kinds = set(folder.get("share_kinds") or [])
    if not kinds:
        kinds = set(share_kinds_for_collection_ids(fixtures, folder.get("collection_ids") or []))
    kinds.discard("Private")

    dep_ids: set[str] = set()
    proj_ids: set[str] = set()
    scope = folder.get("scope") if isinstance(folder.get("scope"), dict) else {}

    def _ingest_entry(entry: dict[str, Any]) -> None:
        for d in entry.get("department_ids") or []:
            s = str(d).strip()
            if s:
                dep_ids.add(s)
        for p in entry.get("project_ids") or []:
            s = str(p).strip()
            if s:
                proj_ids.add(s)
        tgt = str(entry.get("target") or "").strip().lower()
        if tgt == "department":
            kinds.add("DeptPublic" if str(entry.get("access_kind") or "public") == "public" else "DeptLead")
        elif tgt == "project":
            kinds.add("ProjectPublic" if str(entry.get("access_kind") or "public") == "public" else "ProjectLead")
        elif tgt == "company":
            kinds.add("CompanyPublic")
        elif tgt == "management":
            kinds.add("ManagementPublic")

    for entry in scope.get("share_scopes") or []:
        if isinstance(entry, dict):
            _ingest_entry(entry)
    legacy = scope.get("share_add")
    if isinstance(legacy, dict):
        _ingest_entry(legacy)
    for d in scope.get("department_ids") or []:
        s = str(d).strip()
        if s:
            dep_ids.add(s)
    for p in scope.get("project_ids") or []:
        s = str(p).strip()
        if s:
            proj_ids.add(s)

    if not dep_ids and not proj_ids:
        for cid in overlap_sorted:
            c = col_by_id.get(str(cid)) or {}
            st = str(c.get("space_type") or "").strip()
            if st not in {"MultiDeptPublic", "MultiDeptLead", "MultiProjectPublic", "MultiProjectLead"}:
                continue
            scope_row = get_collection_scope(tenant_id, str(cid)) or {}
            if st in {"MultiDeptPublic", "MultiDeptLead"}:
                dep_ids.update(str(x).strip() for x in (scope_row.get("department_ids") or []) if str(x).strip())
            if st in {"MultiProjectPublic", "MultiProjectLead"}:
                proj_ids.update(str(x).strip() for x in (scope_row.get("project_ids") or []) if str(x).strip())
            kinds.add(st)
            break

    return {
        "kinds": sorted(kinds),
        "department_ids": sorted(dep_ids),
        "project_ids": sorted(proj_ids),
    }


def _aggregate_explicit_acl(
    tenant_id: str,
    doc_ids: list[str],
    overlap_sorted: list[str],
    *,
    company_public_default: bool = False,
) -> dict[str, Any]:
    if not doc_ids:
        return {}
    if company_public_default and "c_company_public_1" in overlap_sorted:
        acls = [get_special_doc_acl(tenant_id, d) for d in doc_ids]
        if all(not a for a in acls):
            return {"allow_all": True, "allow_owner": True}
    dims = (
        "allow_all",
        "allow_dept_member",
        "allow_dept_lead",
        "allow_project_member",
        "allow_project_lead",
        "allow_management",
        "allow_owner",
    )
    out: dict[str, Any] = {}
    for dim in dims:
        if dim == "allow_owner":
            out[dim] = True
            continue
        out[dim] = any(bool(get_special_doc_acl(tenant_id, d).get(dim)) for d in doc_ids)
    return out


def _filter_orphan_special_doc_ids(tenant_id: str, candidate_ids: list[str]) -> list[str]:
    """
    「未挂文件夹」桶：仅含曾通过「单篇共享」落到特殊库的文档。
    私人知识库「未归档」文档（仅 owner 私有 collection、无 share 记录）不得进入此列表。
    """
    out: list[str] = []
    for did in candidate_ids:
        did_s = str(did or "").strip()
        if not did_s:
            continue
        if not did_s.startswith("ud_"):
            out.append(did_s)
            continue
        shares = get_doc_share_targets(did_s)
        if any(str((t or {}).get("target_kind") or "").strip() in _SPECIAL_SHARE_TARGET_KINDS for t in shares):
            out.append(did_s)
    return out


def list_special_folder_acl_items(tenant_id: str, fixtures: dict[str, Any]) -> list[dict[str, Any]]:
    """管理后台：按文件夹归集特殊库文档（子树内文档合并为一行）。"""
    from backend.services.kb_folders import collect_subtree_doc_ids, list_folders

    tid = (tenant_id or "").strip() or "tenant1"
    trig = set(SPECIAL_ADMIN_COLLECTION_IDS)
    collections = fixtures.get("collections") or []
    col_by_id = {str((c or {}).get("collection_id") or ""): (c or {}) for c in collections if str((c or {}).get("collection_id") or "")}

    folders = list_folders(tid)
    by_id = {str(f.get("folder_id") or ""): f for f in folders if str(f.get("folder_id") or "")}
    special_folders = []
    for f in folders:
        overlap = set(f.get("collection_ids") or []) & trig
        if overlap:
            special_folders.append((f, sorted(overlap)))

    special_folders.sort(key=lambda pair: _folder_depth(pair[0], by_id), reverse=True)

    doc_to_folder: dict[str, str] = {}
    folder_docs: dict[str, list[str]] = {}
    for f, _overlap in special_folders:
        fid = str(f.get("folder_id") or "").strip()
        if not fid:
            continue
        assigned: list[str] = []
        for did in collect_subtree_doc_ids(tid, fid):
            if did in doc_to_folder:
                continue
            doc_to_folder[did] = fid
            assigned.append(did)
        if assigned:
            folder_docs[fid] = assigned

    items: list[dict[str, Any]] = []
    seen_folder_ids: set[str] = set()
    for f, overlap_sorted in sorted(special_folders, key=lambda pair: str(pair[0].get("name") or "")):
        fid = str(f.get("folder_id") or "").strip()
        if not fid or fid in seen_folder_ids:
            continue
        seen_folder_ids.add(fid)
        doc_ids = folder_docs.get(fid, [])
        if not doc_ids:
            continue
        special_collections = []
        for cid in overlap_sorted:
            c = col_by_id.get(str(cid)) or {}
            name = (c.get("name") or "").strip() if isinstance(c.get("name"), str) else ""
            space_type = (c.get("space_type") or "").strip() if isinstance(c.get("space_type"), str) else ""
            label = name or space_type or str(cid)
            special_collections.append({"collection_id": str(cid), "label": label, "space_type": space_type, "name": name})
        share_scope = _folder_share_scope_from_meta(f, tid, overlap_sorted, col_by_id, fixtures)
        company_default = "c_company_public_1" in overlap_sorted and str(f.get("kind") or "").strip() == "CompanyPublic"
        acl = _aggregate_explicit_acl(tid, doc_ids, overlap_sorted, company_public_default=company_default)
        items.append(
            {
                "folder_id": fid,
                "name": str(f.get("name") or "").strip() or fid,
                "owner_username": str(f.get("owner_username") or "").strip() or None,
                "kind": str(f.get("kind") or "").strip() or None,
                "doc_count": len(doc_ids),
                "doc_ids": doc_ids,
                "special_collection_ids": overlap_sorted,
                "special_collections": special_collections,
                "acl": acl,
                "share_scope": share_scope,
            }
        )

    all_special_docs = {r["doc_id"] for r in list_docs_touching_collections(tid, trig)}
    orphan_ids = _filter_orphan_special_doc_ids(tid, sorted(all_special_docs - set(doc_to_folder.keys())))
    if orphan_ids:
        overlap_union: set[str] = set()
        for did in orphan_ids:
            overlap_union.update(set(get_doc_collection_ids(tid, did)) & trig)
        overlap_sorted = sorted(overlap_union)
        special_collections = []
        for cid in overlap_sorted:
            c = col_by_id.get(str(cid)) or {}
            name = (c.get("name") or "").strip() if isinstance(c.get("name"), str) else ""
            space_type = (c.get("space_type") or "").strip() if isinstance(c.get("space_type"), str) else ""
            label = name or space_type or str(cid)
            special_collections.append({"collection_id": str(cid), "label": label, "space_type": space_type, "name": name})
        kinds: set[str] = set()
        dep_ids: set[str] = set()
        proj_ids: set[str] = set()
        for did in orphan_ids:
            ss = get_doc_share_targets(did)
            for t in ss:
                k = str(t.get("target_kind") or "").strip()
                if k:
                    kinds.add(k)
                meta = t.get("target") if isinstance(t.get("target"), dict) else {}
                for d in meta.get("department_ids") or []:
                    s = str(d).strip()
                    if s:
                        dep_ids.add(s)
                for p in meta.get("project_ids") or []:
                    s = str(p).strip()
                    if s:
                        proj_ids.add(s)
        items.append(
            {
                "folder_id": _UNFILED_SPECIAL_FOLDER_ID,
                "name": "单独共享（未挂文件夹）",
                "owner_username": None,
                "kind": None,
                "doc_count": len(orphan_ids),
                "doc_ids": orphan_ids,
                "special_collection_ids": overlap_sorted,
                "special_collections": special_collections,
                "acl": _aggregate_explicit_acl(tid, orphan_ids, overlap_sorted, company_public_default=False),
                "share_scope": {
                    "kinds": sorted(kinds),
                    "department_ids": sorted(dep_ids),
                    "project_ids": sorted(proj_ids),
                },
                "is_unfiled_bucket": True,
            }
        )

    return items


def apply_special_folder_acl(tenant_id: str, folder_id: str, acl: dict[str, Any], fixtures: dict[str, Any] | None = None) -> int:
    from backend.services.kb_folders import collect_subtree_doc_ids

    tid = (tenant_id or "").strip() or "tenant1"
    fid = (folder_id or "").strip()
    if not fid:
        return 0
    if fid == _UNFILED_SPECIAL_FOLDER_ID:
        trig = set(SPECIAL_ADMIN_COLLECTION_IDS)
        doc_ids = sorted({r["doc_id"] for r in list_docs_touching_collections(tid, trig)})
        from backend.services.kb_folders import list_folders

        covered: set[str] = set()
        for f in list_folders(tid):
            if set(f.get("collection_ids") or []) & trig:
                for did in collect_subtree_doc_ids(tid, str(f.get("folder_id") or "")):
                    covered.add(did)
        doc_ids = [d for d in doc_ids if d not in covered]
    else:
        doc_ids = collect_subtree_doc_ids(tid, fid)
    n = 0
    payload = dict(acl or {})
    payload["allow_owner"] = True
    for did in doc_ids:
        set_special_doc_acl(tid, did, payload)
        n += 1
    return n


def resolve_doc_title(tenant_id: str, doc_id: str, fixtures: dict[str, Any] | None = None) -> str:
    did = str(doc_id)
    if did.startswith("ud_"):
        with get_db() as db:
            row = db.execute(
                text("SELECT title FROM kb_user_documents WHERE tenant_id=:t AND doc_id=:d"),
                {"t": tenant_id, "d": did},
            ).fetchone()
        return str(row[0]) if row and row[0] else did
    if fixtures:
        for d in fixtures.get("documents") or []:
            if str(d.get("doc_id") or "") == did:
                return str(d.get("title") or did)
    return did


def list_rag_packages(tenant_id: str) -> list[dict[str, Any]]:
    with get_db() as db:
        rows = db.execute(
            text(
                """
                SELECT package_id, name, manifest_json, storage_path, owner_username, created_at, created_by_task_id
                FROM kb_rag_packages
                WHERE tenant_id = :t
                ORDER BY created_at DESC
                """
            ),
            {"t": tenant_id},
        ).fetchall()
    out = []
    for r in rows:
        out.append(
            {
                "package_id": str(r[0]),
                "name": str(r[1] or ""),
                "manifest_json": r[2],
                "storage_path": str(r[3] or ""),
                "owner_username": str(r[4] or ""),
                "created_at": r[5].isoformat() if r[5] else None,
                "created_by_task_id": str(r[6] or "") if r[6] else None,
            }
        )
    return out