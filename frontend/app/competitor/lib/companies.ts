import type { CompetitorReportSnapshot, TableBlock } from "./types";

/** 本公司列 canonical 名；表头亦可能写 YYCQ */
export const SUBJECT_COL = "本公司" as const;

/** 竞品财报 MD 表头中的公司列名（canonical） */
export const COMPANY_COLS = [
  SUBJECT_COL,
  "可比公司A",
  "可比公司B",
  "可比公司C",
  "可比公司D",
  "可比公司E",
  "可比公司F",
  "可比公司G",
] as const;

const SUBJECT_ALIASES = new Set<string>([SUBJECT_COL, "YYCQ"]);

export function isSubjectCol(colOrLabel: string): boolean {
  return SUBJECT_ALIASES.has(colOrLabel.trim()) || labelToCol(colOrLabel) === SUBJECT_COL;
}

/** 蓝本中本公司 / YYCQ 的展示名（与上传蓝本一致） */
export function companyDisplayLabel(
  colOrLabel: string,
  snapshot?: CompetitorReportSnapshot,
): string {
  const raw = colOrLabel.trim();
  const col = labelToCol(raw);
  if (col === SUBJECT_COL) {
    const fromSnap = snapshot?.companies.find((c) => c.id === "yycq")?.label?.trim();
    if (fromSnap) return fromSnap;
    if (SUBJECT_ALIASES.has(raw)) return raw === "YYCQ" ? SUBJECT_COL : raw;
    return SUBJECT_COL;
  }
  return raw || col;
}

export function colToLabel(col: string, snapshot?: CompetitorReportSnapshot): string {
  return companyDisplayLabel(col, snapshot);
}

export function labelToCol(label: string): string {
  if (SUBJECT_ALIASES.has(label.trim())) return SUBJECT_COL;
  return label;
}

/** 叙事/匹配用：本公司与 YYCQ 均视为同一主体 */
export function companyMatchLabels(snapshot?: CompetitorReportSnapshot): string[] {
  const subject = companyDisplayLabel(SUBJECT_COL, snapshot);
  return COMPANY_COLS.flatMap((c) => (c === SUBJECT_COL ? [subject, SUBJECT_COL, "YYCQ"] : [c]));
}

/** 表行按公司列取值：兼容本公司 / YYCQ 表头差异 */
export function rowValueForCompany(
  row: Record<string, string | number | null | undefined> | undefined,
  col: string,
): string | number | null | undefined {
  if (!row) return null;
  const keys = col === SUBJECT_COL ? (["本公司", "YYCQ"] as const) : ([col] as const);
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

/** sec-09 客户集中度等：不含本公司的可比公司列序 */
export const PEER_COMPANY_COLS = COMPANY_COLS.slice(1);
