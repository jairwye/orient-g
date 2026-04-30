/**
 * 在“文件夹视图”下，为了即时反馈（不等二次拉取），对 folderDetail 做最小本地补丁。
 *
 * @param {any} folderDetail
 * @param {string} docId
 * @returns {any}
 */
export function optimisticRemoveDocFromFolderDetail(folderDetail, docId) {
  const did = String(docId || "").trim();
  if (!folderDetail || !did) return folderDetail;
  const docs = Array.isArray(folderDetail.docs) ? folderDetail.docs : [];
  const nextDocs = docs.filter((d) => String(d?.doc_id || "").trim() !== did);
  if (nextDocs.length === docs.length) return folderDetail;
  return { ...folderDetail, docs: nextDocs };
}

/**
 * 文件夹视图：右栏顶部标题应该显示当前文件夹名（无“文档/文件夹”分段标题）。
 *
 * @param {{ folderName?: string, folderId?: string }} args
 * @returns {string}
 */
export function folderViewHeading(args) {
  const name = String(args?.folderName || "").trim();
  if (name) return name;
  const fid = String(args?.folderId || "").trim();
  return fid ? `文件夹：${fid}` : "文件夹";
}

