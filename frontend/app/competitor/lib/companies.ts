import type { CompetitorReportSnapshot, TableBlock } from "./types";
import { FK } from "./field_keys";

/** 本公司列 canonical 名；表头亦可能写 YYCQ 或蓝本原文列名 */
export const SUBJECT_COL = "本公司" as const;

/** 竞品财报 MD 表头中的公司列名（canonical；匿名蓝本用 本公司 / 可比公司A…） */
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

const TABLE_NON_COMPANY_HEADERS = new Set<string>([
  FK.metric,
  FK.company,
  FK.productType,
  FK.region,
  FK.subject,
  FK.value,
]);

export function isSubjectCol(colOrLabel: string): boolean {
  return SUBJECT_ALIASES.has(colOrLabel.trim()) || labelToCol(colOrLabel) === SUBJECT_COL;
}

/** 宽表表头中的公司列（排除 指标 / 公司等维度列） */
export function companyColsFromTableHeaders(headers: string[]): string[] {
  return headers.filter((h) => h.trim() && !TABLE_NON_COMPANY_HEADERS.has(h.trim()));
}

/** 优先用表头中的公司列，其次 snapshot.companies，最后匿名 COMPANY_COLS */
export function companyColsForSnapshot(
  snapshot: CompetitorReportSnapshot,
  tableHeaders?: string[],
): string[] {
  const fromHeaders = tableHeaders?.length ? companyColsFromTableHeaders(tableHeaders) : [];
  if (fromHeaders.length > 0) return fromHeaders;
  const labels = snapshot.companies?.map((c) => c.label).filter(Boolean) as string[] | undefined;
  if (labels?.length) return labels;
  return [...COMPANY_COLS];
}

/** 主体列在蓝本中的全部可能行键（含表头原文，不写死内网历史列名） */
export function subjectDataKeys(snapshot?: CompetitorReportSnapshot): string[] {
  const keys = new Set<string>([SUBJECT_COL, "YYCQ"]);
  const yycq = snapshot?.companies?.find((c) => c.id === "yycq");
  if (yycq?.label?.trim()) keys.add(yycq.label.trim());
  if (yycq?.short?.trim()) keys.add(yycq.short.trim());
  if (snapshot) {
    for (const section of snapshot.sections ?? []) {
      for (const block of section.blocks ?? []) {
        if (block.kind !== "table") continue;
        const headers = companyColsFromTableHeaders((block as TableBlock).headers ?? []);
        if (headers[0]) keys.add(headers[0]);
      }
    }
  }
  return [...keys];
}

/** 内网页面主体展示名：以蓝本表头 / snapshot 为准，匿名 canonical「本公司」不在 UI 展示 */
export function subjectUiLabel(snapshot?: CompetitorReportSnapshot): string {
  if (snapshot) {
    for (const section of snapshot.sections ?? []) {
      for (const block of section.blocks ?? []) {
        if (block.kind !== "table") continue;
        const headers = companyColsFromTableHeaders((block as TableBlock).headers ?? []);
        const first = headers[0];
        if (first && first !== SUBJECT_COL) return first;
      }
    }

    const yycq = snapshot.companies?.find((c) => c.id === "yycq");
    const label = yycq?.label?.trim();
    if (label && label !== SUBJECT_COL && !label.startsWith("可比公司")) return label;
    const short = yycq?.short?.trim();
    if (short && short !== SUBJECT_COL) return short;
  }
  return "YYCQ";
}

/** 蓝本列键 → 页面展示名（主体 canonical「本公司」→ 蓝本实际列名） */
export function companyDisplayLabel(
  colOrLabel: string,
  snapshot?: CompetitorReportSnapshot,
): string {
  const raw = colOrLabel.trim();
  if (!isSubjectCol(raw)) {
    return raw || labelToCol(raw);
  }
  if (raw === "YYCQ") return snapshot ? subjectUiLabel(snapshot) : "YYCQ";
  if (snapshot) return subjectUiLabel(snapshot);
  return "YYCQ";
}

export function colToLabel(col: string, snapshot?: CompetitorReportSnapshot): string {
  return companyDisplayLabel(col, snapshot);
}

/** 宽表 DataTable：表头 canonical「本公司」→ 蓝本展示名；取数走 rowValueForCompany */
export function competitorTableUiProps(snapshot: CompetitorReportSnapshot) {
  return {
    headerDisplay: (h: string) => colToLabel(h, snapshot),
    getCellValue: (h: string, row: Record<string, string | number | null>) =>
      rowValueForCompany(row, h, snapshot) ?? row[h],
  } as const;
}

export function labelToCol(label: string): string {
  if (SUBJECT_ALIASES.has(label.trim())) return SUBJECT_COL;
  return label;
}

export type CompanyContext = {
  cols: readonly string[];
  peerCols: readonly string[];
  labels: readonly string[];
  labelsByLength: readonly string[];
  labelOrder: readonly string[];
};

/** 图表 / 叙事 / 分主体解读共用的公司列与展示名上下文 */
export function getCompanyContext(
  snapshot?: CompetitorReportSnapshot,
  tableHeaders?: string[],
): CompanyContext {
  const cols = snapshot
    ? companyColsForSnapshot(snapshot, tableHeaders)
    : tableHeaders?.length
      ? companyColsFromTableHeaders(tableHeaders)
      : [...COMPANY_COLS];
  const labels = cols.map((c) => colToLabel(c, snapshot));
  const fromSnap = snapshot?.companies.flatMap((c) => [c.label, c.short].filter(Boolean) as string[]) ?? [];
  const labelOrder = [...new Set([...labels, ...fromSnap])];
  const labelsByLength = [...labelOrder].sort((a, b) => b.length - a.length);
  const peerCols = cols.filter((c) => !isSubjectCol(c));
  return { cols, peerCols, labels, labelsByLength, labelOrder };
}

export function companyLabelsForSnapshot(
  snapshot?: CompetitorReportSnapshot,
  tableHeaders?: string[],
): string[] {
  return [...getCompanyContext(snapshot, tableHeaders).labels];
}

export function peerCompanyColsForSnapshot(
  snapshot: CompetitorReportSnapshot,
  tableHeaders?: string[],
): string[] {
  return [...getCompanyContext(snapshot, tableHeaders).peerCols];
}

/** sec-09 探索器默认选中第一家可比公司 */
export function defaultPeerCompanyCol(
  snapshot: CompetitorReportSnapshot,
  tableHeaders?: string[],
): string {
  const peers = peerCompanyColsForSnapshot(snapshot, tableHeaders);
  if (peers[0]) return peers[0];
  const names = snapshot.companies?.map((c) => c.label).filter(Boolean) as string[] | undefined;
  return names?.[1] ?? names?.[0] ?? PEER_COMPANY_COLS[0] ?? "";
}

/** 叙事 / 分主体卡片中的展示名 → 表头列键 */
export function colKeyForDisplayLabel(label: string, snapshot?: CompetitorReportSnapshot): string {
  const t = label.trim();
  if (isSubjectCol(t)) {
    const ctx = getCompanyContext(snapshot);
    return ctx.cols.find((c) => isSubjectCol(c)) ?? ctx.cols[0] ?? SUBJECT_COL;
  }
  const hit = snapshot?.companies.find(
    (c) => c.label === t || c.short === t || companyDisplayLabel(c.label, snapshot) === t,
  );
  if (hit) return hit.label;
  return t;
}

export function companyMatchLabels(snapshot?: CompetitorReportSnapshot): string[] {
  const ctx = getCompanyContext(snapshot);
  const extras = [SUBJECT_COL, "YYCQ", "本公司"];
  const fromSnap = snapshot?.companies.flatMap((c) => [c.label, c.short].filter(Boolean) as string[]) ?? [];
  return [...new Set([...ctx.labelOrder, ...extras, ...fromSnap, ...subjectDataKeys(snapshot)])];
}

/** 表行按公司列取值：兼容 canonical 与蓝本原文列键 */
export function rowValueForCompany(
  row: Record<string, string | number | null | undefined> | undefined,
  colOrLabel: string,
  snapshot?: CompetitorReportSnapshot,
): string | number | null | undefined {
  if (!row) return null;
  const trimmed = colOrLabel.trim();
  const col = labelToCol(trimmed);
  if (col === SUBJECT_COL) {
    for (const key of subjectDataKeys(snapshot)) {
      const v = row[key];
      if (v != null && v !== "") return v;
    }
    return null;
  }
  const direct = row[trimmed];
  if (direct != null && direct !== "") return direct;
  const normalized = row[col];
  if (normalized != null && normalized !== "") return normalized;
  return null;
}

/** 保留蓝本表头/行键原文；取数时用 rowValueForCompany + labelToCol */
export function normalizeTableCompanyKeys(table: TableBlock): TableBlock {
  return table;
}

/** sec-09 客户集中度等：不含本公司的可比公司列序 */
export const PEER_COMPANY_COLS = COMPANY_COLS.slice(1);
