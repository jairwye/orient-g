"""将 kb_scope（含 folder_ids）解析为 ask_knowledge / 直接读文档 可用的参数。"""

from __future__ import annotations

from typing import Any


def resolve_kb_scope_for_ask(
    tenant_id: str,
    kb_scope: dict[str, list[str]] | None,
    *,
    attached_doc_ids: list[str] | None = None,
) -> dict[str, Any]:
    """
    与 ai_interaction 一致：folder_ids → collection_ids + 子树 doc_ids。

    返回:
      collection_ids, table_ids, attached_doc_ids（含文件夹内文档）,
      folder_doc_ids, limit_to_attached（仅选文件夹且未显式选集合时限定检索范围）
    """
    scope = kb_scope or {}
    raw_cols = [str(x).strip() for x in (scope.get("selected_collection_ids") or []) if str(x).strip()]
    raw_tables = [str(x).strip() for x in (scope.get("selected_table_ids") or []) if str(x).strip()]
    raw_folders = [str(x).strip() for x in (scope.get("selected_folder_ids") or []) if str(x).strip()]
    attached = [str(x).strip() for x in (attached_doc_ids or []) if str(x).strip()]

    collection_ids = list(raw_cols)
    folder_doc_ids: list[str] = []

    if raw_folders:
        try:
            from backend.services.kb_folders import collect_subtree_doc_ids, list_folders

            folders = list_folders(tenant_id)
            f2c = {str(f.get("folder_id")): list(f.get("collection_ids") or []) for f in folders}
            for fid in raw_folders:
                for cid in f2c.get(fid, []) or []:
                    cc = str(cid).strip()
                    if cc:
                        collection_ids.append(cc)
                folder_doc_ids.extend(collect_subtree_doc_ids(tenant_id, fid))
            folder_doc_ids = list(dict.fromkeys(folder_doc_ids))
        except Exception:
            pass

    seen: set[str] = set()
    collection_ids = [x for x in collection_ids if not (x in seen or seen.add(x))]

    merged_attached = list(dict.fromkeys(attached + folder_doc_ids))
    explicit_collections = bool(raw_cols)
    limit_to_attached = bool(raw_folders) and bool(folder_doc_ids) and not explicit_collections

    return {
        "collection_ids": collection_ids,
        "table_ids": raw_tables,
        "attached_doc_ids": merged_attached,
        "folder_doc_ids": folder_doc_ids,
        "folder_ids": raw_folders,
        "limit_to_attached": limit_to_attached,
    }
