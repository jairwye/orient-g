import type { CompetitorReportSnapshot, TableBlock } from "./types";

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

const YYCQ_ALIASES = new Set(["YYCQ", "游艺春秋"]);

/** 蓝本中 YYCQ / 游艺春秋 的展示名（与上传蓝本一致） */
export function companyDisplayLabel(
  colOrLabel: string,
  snapshot?: CompetitorReportSnapshot,
): string {
  const raw = colOrLabel.trim();
  const col = labelToCol(raw);
  if (col === "YYCQ") {
    const fromSnap = snapshot?.companies.find((c) => c.id === "yycq")?.label?.trim();
    if (fromSnap) return fromSnap;
    if (YYCQ_ALIASES.has(raw)) return raw;
    return raw || "YYCQ";
  }
  return raw || col;
}

export function colToLabel(col: string, snapshot?: CompetitorReportSnapshot): string {
  return companyDisplayLabel(col, snapshot);
}

export function labelToCol(label: string): string {
  if (label === "游艺春秋" || label === "YYCQ") return "YYCQ";
  return label;
}

/** 叙事/匹配用：YYCQ 与游艺春秋均视为同一主体 */
export function companyMatchLabels(snapshot?: CompetitorReportSnapshot): string[] {
  const yycq = companyDisplayLabel("YYCQ", snapshot);
  return COMPANY_COLS.flatMap((c) => (c === "YYCQ" ? [yycq, "YYCQ", "游艺春秋"] : [c]));
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

/** 保留蓝本表头/行键原文；取数时用 rowValueForCompany + labelToCol */
export function normalizeTableCompanyKeys(table: TableBlock): TableBlock {
  return table;
}
