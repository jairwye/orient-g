/**
 * 知识库左侧树：按 parent_folder_id 组层级；子文件夹可跨 kind（与 DB 一致）。
 */

const KB_KIND_PRIVATE = "Private";

/**
 * @param {{ kind?: string | null } | null | undefined} f
 */
export function folderKbKind(f) {
  return String(f?.kind || KB_KIND_PRIVATE).trim() || KB_KIND_PRIVATE;
}

/**
 * 子树文档总数（检索/勾选范围用，勿用于树节点角标）。
 * @param {{ subtree_doc_count?: number; resource_counts?: { doc?: number } } | null | undefined} f
 */
export function folderSubtreeDocCount(f) {
  if (f && typeof f.subtree_doc_count === "number") return f.subtree_doc_count;
  return f?.resource_counts?.doc ?? 0;
}

/**
 * 树节点角标：本文件夹直接文档数；若无文档则显示直接子文件夹数量（不把后代文档累加到父级）。
 * @param {{ folder_id?: string; resource_counts?: { doc?: number } } | null | undefined} f
 * @param {Parameters<typeof folderChildrenOf>[0]} folders
 */
export function folderTreeBadgeCount(f, folders) {
  const direct = f?.resource_counts?.doc ?? 0;
  if (direct > 0) return direct;
  const fid = String(f?.folder_id || "").trim();
  if (!fid) return 0;
  return folderChildrenOf(folders || [], fid).length;
}

/**
 * @param {Array<{ folder_id?: string; parent_folder_id?: string | null; name?: string; kind?: string | null }>} folders
 * @param {string | null} parentId
 * @returns {typeof folders}
 */
export function folderChildrenAt(folders, parentId) {
  return folderChildrenOf(folders, parentId);
}

/**
 * 某父节点下所有子文件夹（不按 kind 过滤，避免子级 kind 与父级不一致时消失）。
 * @param {Array<{ folder_id?: string; parent_folder_id?: string | null; name?: string }>} folders
 * @param {string | null} parentId
 */
export function folderChildrenOf(folders, parentId) {
  const pid = parentId || null;
  return (folders || [])
    .filter((f) => (f.parent_folder_id || null) === pid)
    .sort((a, b) => String(a.name || "").localeCompare(String(b.name || ""), "zh"));
}

/**
 * 某知识库类型下的顶层节点：kind 匹配且父级不在「同 kind 可见父链」中。
 * @param {Array<{ folder_id?: string; parent_folder_id?: string | null; kind?: string | null }>} folders
 * @param {string} kbKind
 */
export function kbKindRootFolders(folders, kbKind) {
  const kind = String(kbKind || "").trim() || KB_KIND_PRIVATE;
  const byId = new Map(
    (folders || []).map((f) => [String(f.folder_id || "").trim(), f]).filter(([id]) => id),
  );
  return (folders || [])
    .filter((f) => {
      if (folderKbKind(f) !== kind) return false;
      const parentId = String(f.parent_folder_id || "").trim();
      if (!parentId) return true;
      const parent = byId.get(parentId);
      if (!parent) return true;
      return folderKbKind(parent) !== kind;
    })
    .sort((a, b) => String(a.name || "").localeCompare(String(b.name || ""), "zh"));
}

/**
 * 私人知识库展开后的同级入口：未归档 + 顶层文件夹。
 * @param {Parameters<typeof kbKindRootFolders>[0]} folders
 * @param {number} unfiledCount
 */
export function privateKbRootEntries(folders, unfiledCount) {
  const roots = kbKindRootFolders(folders, KB_KIND_PRIVATE);
  return [{ type: "unfiled", count: unfiledCount }, ...roots.map((folder) => ({ type: "folder", folder }))];
}

/**
 * 搜索时保留匹配项及其祖先，避免树断层。
 * @param {Array<{ folder_id?: string; parent_folder_id?: string | null; name?: string }>} folders
 * @param {string} q
 */
export function filterFoldersForTreeSearch(folders, q) {
  const needle = String(q || "").trim().toLowerCase();
  if (!needle) return folders || [];
  const list = folders || [];
  const matched = new Set();
  for (const f of list) {
    const blob = `${f.name || ""} ${f.folder_id || ""}`.toLowerCase();
    if (blob.includes(needle)) matched.add(String(f.folder_id || "").trim());
  }
  const keep = new Set(matched);
  for (const id of matched) {
    for (const a of folderAncestorIds(list, id)) keep.add(a);
  }
  return list.filter((f) => keep.has(String(f.folder_id || "").trim()));
}

/**
 * @param {Array<{ folder_id?: string; parent_folder_id?: string | null }>} folders
 * @param {string} folderId
 * @returns {string[]}
 */
export function folderAncestorIds(folders, folderId) {
  const byId = new Map((folders || []).map((f) => [String(f.folder_id || "").trim(), f]));
  const out = [];
  let cur = String(folderId || "").trim();
  const seen = new Set();
  while (cur && !seen.has(cur)) {
    seen.add(cur);
    const row = byId.get(cur);
    const parent = String(row?.parent_folder_id || "").trim();
    if (!parent) break;
    out.unshift(parent);
    cur = parent;
  }
  return out;
}

/**
 * @param {string} kbKind
 * @param {string | null} activeKbKind
 * @param {{ kind: string; kb_kind?: string; folder_id?: string }} selection
 */
export function isKbKindTreeExpanded(kbKind, activeKbKind, selection) {
  if (kbKind === activeKbKind) return true;
  if (selection.kind === "folder" && selection.kb_kind === kbKind) return true;
  return false;
}
