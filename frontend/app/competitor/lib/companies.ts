import type { TableBlock } from "./types";

/** 竞品财报 MD 表头中的公司列名（canonical；蓝本亦可能写「游艺春秋」） */
export const COMPANY_COLS = [
  "YYCQ",
  "三七互娱",
  "完美世界",
  "掌趣科技",
  "塔人网络",
  "华清飞扬",
  "像素软件",
  "绿岸网络",
] as const;

export function colToLabel(col: string): string {
  return col === "YYCQ" ? "游艺春秋" : col;
}

export function labelToCol(label: string): string {
  if (label === "游艺春秋" || label === "YYCQ") return "YYCQ";
  return label;
}

/** 表行按公司列取值：兼容 YYCQ / 游艺春秋 表头差异 */
export function rowValueForCompany(
  row: Record<string, string | number | null | undefined> | undefined,
  col: string,
): string | number | null | undefined {
  if (!row) return null;
  const keys = col === "YYCQ" ? (["YYCQ", "游艺春秋"] as const) : ([col] as const);
  for (const key of keys) {
    const v = row[key];
    if (v != null && v !== "") return v;
  }
  return null;
}

/** 将 snapshot 表头/行键归一化为 COMPANY_COLS  canonical 列名 */
export function normalizeTableCompanyKeys(table: TableBlock): TableBlock {
  const headers = table.headers.map((h) => labelToCol(h));
  const rows = table.rows.map((row) => {
    const out: Record<string, string | number | null> = {};
    for (const [k, v] of Object.entries(row)) {
      out[labelToCol(k)] = v;
    }
    return out;
  });
  return { ...table, headers, rows };
}
