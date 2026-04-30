/**
 * @typedef {string | undefined | null} SourceFolderId
 */

/**
 * @param {SourceFolderId} sourceFolderId
 * @returns {string | null}
 */
export function normalizeSourceFolderId(sourceFolderId) {
  if (sourceFolderId == null) return null;
  const s = String(sourceFolderId).trim();
  return s === "" ? null : s;
}

/**
 * @param {SourceFolderId} a
 * @param {SourceFolderId} b
 */
export function isSameSelectionContext(a, b) {
  return normalizeSourceFolderId(a) === normalizeSourceFolderId(b);
}

/**
 * @param {SourceFolderId} sourceFolderId
 * @returns {{kind:"hard_delete"} | {kind:"unlink_from_folder", folder_id: string}}
 */
export function deleteSemanticsForContext(sourceFolderId) {
  const folderId = normalizeSourceFolderId(sourceFolderId);
  if (folderId === null) return { kind: "hard_delete" };
  return { kind: "unlink_from_folder", folder_id: folderId };
}

