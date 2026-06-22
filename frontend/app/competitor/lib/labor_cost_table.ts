import { createElement, type ReactNode } from "react";
import type { CompetitorReportSnapshot, TableBlock } from "./types";
import { companyDisplayLabel } from "./companies";
import { FK } from "./field_keys";
import {
  formatLaborCostDataValue,
  getLaborCostCellValue,
  isLaborCostSectionRow,
  type LaborCostRow,
} from "./labor_cost_table_utils";
import { hasMarkdownBold, renderBoldMarkdown } from "./markdown_bold";

export {
  isLaborCostSectionRow,
  getLaborCostCellValue,
  formatLaborCostDataValue,
};

export function formatLaborCostCell(
  header: string,
  value: string | number | null | undefined,
  row?: LaborCostRow,
  metricKey = FK.metric,
): ReactNode {
  if (header === metricKey) {
    const raw = value == null ? "" : String(value);
    if (hasMarkdownBold(raw)) return renderBoldMarkdown(raw);
    if (!raw) return "";
    return createElement("span", { className: "pl-3 text-zinc-400" }, raw);
  }
  const metric = String(row?.[metricKey] ?? "");
  const cellValue = row ? getLaborCostCellValue(row, header, metricKey) : value;
  return formatLaborCostDataValue(metric, cellValue);
}

export function laborCostTableProps(table: TableBlock, snapshot: CompetitorReportSnapshot) {
  const metricKey = FK.metric;
  return {
    headers: table.headers,
    rows: table.rows,
    compact: true as const,
    headerDisplay: (h: string) => (h === metricKey ? h : companyDisplayLabel(h, snapshot)),
    getCellValue: (h: string, row: Record<string, string | number | null>) =>
      getLaborCostCellValue(row, h, metricKey) ?? null,
    formatCell: (h: string, v: string | number | null, row?: Record<string, string | number | null>) =>
      formatLaborCostCell(h, v, row, metricKey),
    isSectionHeaderRow: (row: Record<string, string | number | null>) =>
      isLaborCostSectionRow(row, table.headers, metricKey),
    rowLabelHeader: metricKey,
    sectionHeaderClassName: "border-t border-zinc-700/60",
  };
}
