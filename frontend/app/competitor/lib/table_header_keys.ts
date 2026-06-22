/** 重复表头列 → 唯一 row 键（与 backend _header_cell_keys 一致） */
export function resolveTableHeaderKeys(headers: string[], headerKeys?: string[]): string[] {
  if (headerKeys?.length === headers.length) return headerKeys;
  const seen = new Map<string, number>();
  return headers.map((h) => {
    const n = seen.get(h) ?? 0;
    seen.set(h, n + 1);
    return n === 0 ? h : `${h}__${n + 1}`;
  });
}
