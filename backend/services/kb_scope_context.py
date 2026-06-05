"""KB 范围上下文：文件夹→文档归属，供多公司横比时标注来源（不缩小 ACL 范围）。"""

from __future__ import annotations

from typing import Any


def _subtree_folder_ids(
    tenant_id: str,
    root_folder_ids: list[str],
) -> list[str]:
    from backend.services.kb_folders import list_folders

    folders = list_folders(tenant_id)
    children_map: dict[str, list[str]] = {}
    known: set[str] = set()
    for f in folders:
        fid = str(f.get("folder_id") or "").strip()
        if not fid:
            continue
        known.add(fid)
        parent = str(f.get("parent_folder_id") or "").strip() or None
        if parent:
            children_map.setdefault(parent, []).append(fid)

    out: list[str] = []
    seen: set[str] = set()
    stack = [x for x in root_folder_ids if x in known or True]
    while stack:
        fid = stack.pop()
        if not fid or fid in seen:
            continue
        seen.add(fid)
        out.append(fid)
        for child in children_map.get(fid, []):
            stack.append(child)
    return out


def build_scope_folder_context(
    tenant_id: str,
    *,
    selected_folder_ids: list[str] | None,
) -> dict[str, Any]:
    """
    解析用户所选文件夹子树内 doc→子文件夹名。
    multi_company_scope：子树内≥2 个文件夹直接绑定了文档（竞品总夹横比场景）。
    """
    roots = [str(x).strip() for x in (selected_folder_ids or []) if str(x).strip()]
    if not roots:
        return {
            "doc_folder_labels": {},
            "scope_folders": [],
            "multi_company_scope": False,
        }

    from backend.services.kb_folders import list_folders, list_folder_user_doc_ids

    tid = (tenant_id or "").strip() or "tenant1"
    all_folders = list_folders(tid)
    id_to_name = {
        str(f.get("folder_id") or "").strip(): str(f.get("name") or f.get("folder_id") or "").strip()
        for f in all_folders
        if str(f.get("folder_id") or "").strip()
    }

    subtree_ids = _subtree_folder_ids(tid, roots)
    doc_labels: dict[str, str] = {}
    folders_with_docs: list[str] = []

    for fid in subtree_ids:
        docs = list_folder_user_doc_ids(tid, folder_id=fid)
        if docs:
            folders_with_docs.append(fid)
        label = id_to_name.get(fid, fid)
        for did in docs:
            doc_labels.setdefault(str(did), label)

    scope_folders = [
        {"folder_id": fid, "name": id_to_name.get(fid, fid)}
        for fid in sorted(set(folders_with_docs), key=lambda x: id_to_name.get(x, x))
    ]
    multi = len(scope_folders) > 1

    return {
        "doc_folder_labels": doc_labels,
        "scope_folders": scope_folders,
        "multi_company_scope": multi,
    }


def multi_company_scope_addon(evidence_pack: dict[str, Any] | None) -> str:
    pack = evidence_pack or {}
    if not pack.get("multi_company_scope"):
        return ""
    names = [
        str(f.get("name") or "").strip()
        for f in (pack.get("scope_folders") or [])
        if isinstance(f, dict) and str(f.get("name") or "").strip()
    ]
    if not names:
        return ""
    shown = "、".join(names[:12])
    if len(names) > 12:
        shown += f" 等 {len(names)} 个"
    return (
        f"【多主体范围】当前检索范围含多个子文件夹（{shown}）。"
        "证据节选已标注 `[来源: 文件夹名]`；横比或对比表请按公司/文件夹分列，"
        "禁止混用不同主体的数字。若缺某家数据，请再调用 orientg_kb_ask 并带上该公司或文件夹名。\n"
    )
