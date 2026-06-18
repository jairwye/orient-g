const FILL_DOWN_HEADERS = ["竞企名称", "公司", "公司名称"] as const;

/** 蓝本表格合并单元格：向下填充主体列 */
export function fillDownTableRows(
  rows: Record<string, string | number | null>[],
  headers: string[],
): Record<string, string | number | null>[] {
  const key = FILL_DOWN_HEADERS.find((h) => headers.includes(h));
  if (!key || !rows.length) return rows;

  let last = "";
  return rows.map((row) => {
    const raw = String(row[key] ?? "").trim();
    if (raw && raw !== "—" && raw !== "-" && !raw.startsWith("**")) last = raw;
    return { ...row, [key]: last || raw };
  });
}
