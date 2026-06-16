/** 雷达图公司勾选：默认全选 → 首次点击单选 → 同项再点取消 → 点其他项多选 */
export function toggleRadarCompanySelection(
  allCompanies: readonly string[],
  selected: ReadonlySet<string>,
  company: string,
): Set<string> {
  const allSelected =
    allCompanies.length > 0 && allCompanies.every((c) => selected.has(c));

  if (allSelected) {
    return new Set([company]);
  }

  if (selected.size === 1 && selected.has(company)) {
    return new Set();
  }

  const next = new Set(selected);
  if (next.has(company)) {
    next.delete(company);
  } else {
    next.add(company);
  }
  return next;
}

export function isAllRadarCompaniesSelected(
  allCompanies: readonly string[],
  selected: ReadonlySet<string>,
): boolean {
  return allCompanies.length > 0 && allCompanies.every((c) => selected.has(c));
}
