/**
 * Pin and sort kb kind ids.
 * @param {string[]} kinds
 * @returns {string[]}
 */
export function sortKbKindsPinned(kinds) {
  const seen = new Set();
  const arr = Array.isArray(kinds) ? kinds.map((x) => String(x || "").trim()).filter(Boolean) : [];
  const unique = [];
  for (const k of arr) {
    if (seen.has(k)) continue;
    seen.add(k);
    unique.push(k);
  }
  const pinned = ["Private", "CompanyPublic"].filter((k) => unique.includes(k));
  const rest = unique.filter((k) => !pinned.includes(k));
  return [...pinned, ...rest];
}

