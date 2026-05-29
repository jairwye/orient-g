"""
直接文档读取引擎：当用户显式引用文档/文件夹时，直接从磁盘读取文档内容，
绕过 RAG 检索，将完整内容注入 LLM 上下文。

适用场景：
- 用户通过 "带到 AI 互动" 引用文档
- 用户在输入框上传文件后引用
- 用户选择文件夹作为上下文
- 未来：流程文档集合的批量读取
"""

from __future__ import annotations

import json
from typing import Any

from backend.services.kb_documents import _doc_root


def resolve_doc_ids_from_context(
    tenant_id: str,
    *,
    attached_doc_ids: list[str] | None = None,
    folder_ids: list[str] | None = None,
) -> list[str]:
    """
    将所有引用来源统一解析为去重的 doc_id 列表。

    - attached_doc_ids: 用户显式带到 AI 的文档（来自 composerAttachments）
    - folder_ids: 用户选择的文件夹 → 内部解析为文档列表
    """
    doc_ids: list[str] = []
    seen: set[str] = set()

    # 1. 显式引用的文档
    for did in (attached_doc_ids or []):
        d = str(did).strip()
        if d and d not in seen:
            doc_ids.append(d)
            seen.add(d)

    # 2. 文件夹 → 解析为文档列表（含所有后代子文件夹）
    for fid in (folder_ids or []):
        fid_s = str(fid).strip()
        if not fid_s:
            continue
        try:
            from backend.services.kb_folders import collect_subtree_doc_ids

            for did in collect_subtree_doc_ids(tenant_id, fid_s):
                if did not in seen:
                    doc_ids.append(did)
                    seen.add(did)
        except Exception:
            pass

    return doc_ids


def read_document_content(
    tenant_id: str,
    doc_id: str,
    *,
    max_chars: int = 12000,
) -> str | None:
    """
    从磁盘读取单个文档的完整内容。

    策略（按优先级）：
    1. archive/full.md 全文（≤ max_chars 时全文；超过则头尾截断）
    2. kb/sections/*.md 逐个拼接（回退，用于 full.md 不存在或不完整的情况）
    3. 都不存在 → 返回 None（文档尚未解析完成）

    返回: 文档文本内容，或 None
    """
    # 路径穿越防护：仅允许 ud_ 前缀的合法文档 ID
    did = str(doc_id or "").strip()
    if not did or ".." in did or "/" in did or "\\" in did:
        return None
    if not did.startswith("ud_"):
        return None

    root = _doc_root(tenant_id, did)

    # 首选：完整 MD
    full_md = root / "archive" / "full.md"
    if full_md.exists():
        try:
            text = full_md.read_text(encoding="utf-8", errors="replace")
        except Exception:
            text = ""
        if not text.strip():
            # 空文件，继续尝试 sections
            pass
        elif len(text) <= max_chars:
            return text
        else:
            # 大文件：头尾各取一半
            half = max_chars // 2
            return text[:half] + "\n\n...(中间内容省略)...\n\n" + text[-half:]

    # 回退：逐个读取 sections
    sections_dir = root / "kb" / "sections"
    if sections_dir.exists():
        try:
            # 先读 manifest 获取标题
            titles: dict[str, str] = {}
            manifest_path = root / "kb" / "manifest.json"
            if manifest_path.exists():
                try:
                    m = json.loads(manifest_path.read_text(encoding="utf-8"))
                    for s in m.get("sections") or []:
                        titles[str(s.get("filename") or "")] = str(s.get("title") or "")
                except Exception:
                    pass

            parts: list[str] = []
            total = 0
            section_files = sorted(sections_dir.glob("s*.md"))
            for sf in section_files:
                if total >= max_chars:
                    remaining = len(section_files) - len(parts)
                    if remaining > 0:
                        parts.append(f"\n...(剩余 {remaining} 节省略)...")
                    break
                try:
                    t = sf.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue
                title = titles.get(sf.name, sf.stem)
                parts.append(f"## {title}\n{t}")
                total += len(t)
            return "\n\n".join(parts)[:max_chars] if parts else None
        except Exception:
            return None

    return None


def load_document_meta(
    tenant_id: str,
    doc_id: str,
) -> dict[str, Any] | None:
    """
    从数据库获取文档标题和状态。
    返回: {"doc_id", "title", "status"} 或 None
    """
    try:
        from sqlalchemy import text

        from backend.database import get_db

        with get_db() as db:
            row = db.execute(
                text(
                    "SELECT doc_id, title, original_filename, status "
                    "FROM kb_user_documents WHERE tenant_id=:t AND doc_id=:d"
                ),
                {"t": tenant_id, "d": doc_id},
            ).fetchone()
        if row:
            return {
                "doc_id": str(row[0]),
                "title": str(row[1] or row[2] or row[0]),
                "status": str(row[3] or ""),
            }
    except Exception:
        pass
    return None


def assemble_document_context(
    tenant_id: str,
    doc_ids: list[str],
    *,
    max_total_chars: int = 40000,
    max_per_doc: int = 12000,
) -> tuple[str, list[str]]:
    """
    读取所有文档内容并拼接为 LLM 上下文。

    返回: (context_text, skipped_doc_titles)
      - context_text: 格式化的文档内容块
      - skipped_doc_titles: 跳过（未解析/无法读取）的文档标题列表
    """
    parts: list[str] = []
    total = 0
    skipped: list[str] = []

    for did in doc_ids:
        if total >= max_total_chars:
            remaining = len(doc_ids) - len(parts) - len(skipped)
            if remaining > 0:
                parts.append(f"\n...(还有 {remaining} 篇文档因长度限制省略)...")
            break

        meta = load_document_meta(tenant_id, did)
        title = meta.get("title", did) if meta else did
        status = meta.get("status", "") if meta else ""

        content = read_document_content(tenant_id, did, max_chars=max_per_doc)
        if not content:
            if status and status not in ("active", "packaged", "parsed"):
                skipped.append(f"{title}（状态 {status}，未完成解析或无 sections/full.md）")
            else:
                skipped.append(title)
            continue

        doc_block = f"[文档: {title}]\n{content}"
        parts.append(doc_block)
        total += len(doc_block)

    return "\n\n---\n\n".join(parts), skipped
