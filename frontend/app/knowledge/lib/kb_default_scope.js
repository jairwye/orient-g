/**
 * Compute default selected kb kinds in the required order.
 * Order: Private, DeptPublic, ProjectPublic (optional), CompanyPublic.
 *
 * @param {{ availableKinds: string[], hasProjectAccess: boolean }} args
 * @returns {string[]}
 */
export function computeDefaultScopeKinds(args) {
  const available = new Set((args?.availableKinds || []).map((x) => String(x || "").trim()).filter(Boolean));
  const hasProject = Boolean(args?.hasProjectAccess);
  const want = ["Private", "DeptPublic", hasProject ? "ProjectPublic" : null, "CompanyPublic"].filter(Boolean);
  return want.filter((k) => available.has(k));
}

