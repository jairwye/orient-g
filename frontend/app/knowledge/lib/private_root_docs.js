/**
 * 私人知识库「未归档 / 根级」文档判定。
 * 未归档 = 未绑定任何用户可见文件夹（忽略内部 f_private_* 系统文件夹）。
 */

/**
 * @param {string} folderId
 * @returns {boolean}
 */
export function isInternalPrivateFolderId(folderId) {
  const fid = String(folderId || "").trim();
  return fid.startsWith("f_private_");
}

/**
 * @param {Array<{ folder_id?: string }>} folders
 * @returns {Set<string>}
 */
export function visibleFolderIdSet(folders) {
  const out = new Set();
  for (const f of folders || []) {
    const fid = String(f?.folder_id || "").trim();
    if (!fid || isInternalPrivateFolderId(fid)) continue;
    out.add(fid);
  }
  return out;
}

/**
 * @param {string | undefined | null} status
 * @returns {boolean}
 */
export function docIsActiveStatus(status) {
  return String(status || "").toLowerCase() === "active";
}

/**
 * @param {string | undefined | null} status
 * @returns {boolean}
 */
export function docIsRunningStatus(status) {
  const s = String(status || "").toLowerCase();
  return (
    s === "uploaded" ||
    s === "queued" ||
    s === "running" ||
    s === "packaging" ||
    s === "processing" ||
    s === "parsing" ||
    s === "parsed" ||
    s === "packaged"
  );
}

/**
 * @param {{ folder_ids?: string[] }} doc
 * @returns {string[]}
 */
export function nonInternalFolderBindings(doc) {
  const fids = Array.isArray(doc?.folder_ids) ? doc.folder_ids : [];
  return fids
    .map((x) => String(x || "").trim())
    .filter((fid) => fid && !isInternalPrivateFolderId(fid));
}

/**
 * @param {{ folder_ids?: string[] }} doc
 * @param {Set<string>} visibleIds
 * @returns {string[]}
 */
export function visibleFolderBindings(doc, visibleIds) {
  return nonInternalFolderBindings(doc).filter((fid) => visibleIds.has(fid));
}

/**
 * @param {{ folder_ids?: string[]; status?: string }} doc
 * @param {Set<string>} [_visibleIds]
 * @param {{ includeRunning?: boolean }} [opts]
 * @returns {boolean}
 */
export function isUnfiledPrivateDoc(doc, _visibleIds, opts) {
  const includeRunning = opts?.includeRunning !== false;
  const status = doc?.status;
  const statusOk = docIsActiveStatus(status) || (includeRunning && docIsRunningStatus(status));
  if (!statusOk) return false;
  // 任意非内部 folder 绑定即视为已归档，不依赖 visibleIds 是否已加载
  return nonInternalFolderBindings(doc).length === 0;
}

/**
 * 文件夹视图：表头全选状态。
 * @param {string[]} allDocIds
 * @param {string[]} selectedDocIds
 * @returns {"none"|"all"|"partial"}
 */
export function folderBulkCheckState(allDocIds, selectedDocIds) {
  const all = (allDocIds || []).filter(Boolean);
  const sel = new Set((selectedDocIds || []).filter(Boolean));
  if (!all.length) return "none";
  const hit = all.filter((id) => sel.has(id)).length;
  if (hit === 0) return "none";
  if (hit === all.length) return "all";
  return "partial";
}

/**
 * 点击表头 checkbox：none/partial -> all；all -> none。
 * @param {"none"|"all"|"partial"} state
 * @param {string[]} allDocIds
 * @returns {string[]}
 */
export function folderBulkToggleAll(state, allDocIds) {
  const all = (allDocIds || []).filter(Boolean);
  if (state === "all") return [];
  return [...all];
}
