/**
 * @typedef {{ kind: "kb", kb_kind: string } | { kind: "folder", kb_kind: string, folder_id: string }} KbSelection
 */

/**
 * Normalize selection object.
 * - trims ids
 * - drops invalid folder_id
 * @param {any} sel
 * @returns {KbSelection}
 */
export function normalizeSelection(sel) {
  const kind = String(sel?.kind || "kb").trim();
  const kb_kind = String(sel?.kb_kind || "Private").trim() || "Private";
  if (kind === "folder") {
    const folder_id = String(sel?.folder_id || "").trim();
    if (folder_id) return { kind: "folder", kb_kind, folder_id };
  }
  return { kind: "kb", kb_kind };
}

