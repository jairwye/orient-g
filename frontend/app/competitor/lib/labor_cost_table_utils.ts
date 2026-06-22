import { labelToCol, rowValueForCompany, SUBJECT_COL } from "./companies";
import { FK } from "./field_keys";
import { formatDecimal2 } from "./format";

export type LaborCostRow = Record<string, string | number | null | undefined>;

const LABOR_COST_SECTION_TITLES = new Set([
  "人力成本",
  "职工福利",
  "工会经费及教育经费",
]);

function laborCostMetricPlain(metric: string): string {
  return metric.replace(/\*\*/g, "").trim();
}

/** sec-04-3 是否含职工福利 / 工会经费分组（完整蓝本 ≥8 行） */
export function laborCostTableHasFullSections(rows: LaborCostRow[], metricKey = FK.metric): boolean {
  const plain = rows.map((r) => laborCostMetricPlain(String(r[metricKey] ?? "")));
  return plain.some((m) => m.includes("职工福利")) && plain.some((m) => m.includes("工会经费"));
}

/** sec-04-3：指标列 **分组标题** 且各公司列为空 */
export function isLaborCostSectionRow(
  row: LaborCostRow,
  headers: string[],
  metricKey = FK.metric,
): boolean {
  const metric = String(row[metricKey] ?? "");
  const plain = laborCostMetricPlain(metric);
  const isSection =
    metric.includes("**") || LABOR_COST_SECTION_TITLES.has(plain) || /^工会经费/.test(plain);
  if (!isSection) return false;
  return headers
    .filter((h) => h !== metricKey)
    .every((h) => {
      const v = getLaborCostCellValue(row, h, metricKey);
      return v == null || v === "";
    });
}

export function getLaborCostCellValue(
  row: LaborCostRow,
  header: string,
  metricKey = FK.metric,
): string | number | null | undefined {
  if (header === metricKey) return row[metricKey];
  const col = labelToCol(header);
  if (col === SUBJECT_COL) return rowValueForCompany(row, SUBJECT_COL);
  return row[header] ?? row[col];
}

/** 按指标行格式化数值（与蓝本 sec-04-3 一致） */
export function formatLaborCostDataValue(
  metric: string,
  value: string | number | null | undefined,
): string {
  if (value == null || value === "") return "—";
  if (typeof value === "string") {
    const t = value.trim();
    if (!t || t === "—" || t === "-") return "—";
    return t;
  }
  if (!Number.isFinite(value)) return "—";
  if (value === 0) return "0";

  const m = metric.trim();
  if (/人均\(元\/年\)/.test(m)) {
    return formatDecimal2(value);
  }
  if (/增减变动/.test(m)) {
    if (value > 0) return `+${formatDecimal2(value)}`;
    return formatDecimal2(value);
  }
  return formatDecimal2(value);
}
