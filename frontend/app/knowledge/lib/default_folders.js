/**
 * Decide dept default folder name for a user.
 * @param {{username: string | undefined | null, existingNames: string[], candidates: string[]}} args
 * @returns {string | null}
 */
export function pickDeptDefaultFolderName(args) {
  const username = String(args?.username || "").trim();
  if (username !== "wangjia") return null;
  const existing = new Set((args?.existingNames || []).map((x) => String(x || "").trim()).filter(Boolean));
  const candidates = (args?.candidates || []).map((x) => String(x || "").trim()).filter(Boolean);
  for (const c of candidates) {
    if (!existing.has(c)) return c;
  }
  return null;
}

