import type { CompetitorReportSnapshot } from "./types";
import { rowValueForCompany, wideSubjectLabel } from "./companies";
import { parseNum } from "./format";

type AssetTable = {
  headers: string[];
  rows: Array<Record<string, string | number | null | undefined>>;
} | null | undefined;

/** 去掉空白与行尾单位后缀，便于「货币资金」与「货币资金(万)」等价。 */
export function normalizeAssetSubjectLabel(label: string): string {
  return label.replace(/\s/g, "").replace(/[(（][^)）]*[)）]$/u, "");
}

/**
 * 匹配分：精确(去单位) > 前缀；禁止裸 includes，避免「其他货币资金」误命中「货币资金」。
 */
export function scoreAssetSubjectMatch(label: string, subjectPrefix: string): number {
  const normalized = normalizeAssetSubjectLabel(label);
  const prefix = subjectPrefix.replace(/\s/g, "");
  if (!prefix || !normalized) return 0;
  if (normalized === prefix) return 3;
  if (normalized.startsWith(prefix)) return 2;
  return 0;
}

/** 图表轴是「亿」。行名带（亿）时原值已是亿；否则按万元换算。 */
export function assetAmountToYi(raw: number, label: string): number {
  if (label.includes("(\u4ebf)") || label.includes("\uff08\u4ebf\uff09")) return raw;
  return raw / 10000;
}

export function assetRowValue(
  table: AssetTable,
  subjectPrefix: string,
  col: string,
  snapshot?: CompetitorReportSnapshot,
): { value: number; label: string } | null {
  if (!table?.rows?.length) return null;

  let best: (typeof table.rows)[number] | null = null;
  let bestScore = 0;
  for (const row of table.rows) {
    const label = wideSubjectLabel(row, table.headers);
    const score = scoreAssetSubjectMatch(label, subjectPrefix);
    if (score > bestScore) {
      bestScore = score;
      best = row;
    }
  }
  if (!best || bestScore === 0) return null;

  const label = wideSubjectLabel(best, table.headers);
  const value = parseNum(rowValueForCompany(best, col, snapshot));
  if (value == null) return null;
  return { value, label };
}

export function buildCashDebtChartRows(
  table: AssetTable,
  cols: string[],
  snapshot: CompetitorReportSnapshot | undefined,
  nameForCol: (col: string) => string,
): Array<{ name: string; cash: number; debt: number }> {
  return cols
    .map((col) => {
      const cash = assetRowValue(table, "\u8d27\u5e01\u8d44\u91d1", col, snapshot);
      const debt = assetRowValue(table, "\u77ed\u671f\u501f\u6b3e", col, snapshot);
      if (cash == null && debt == null) return null;
      return {
        name: nameForCol(col),
        cash: cash ? assetAmountToYi(cash.value, cash.label) : 0,
        debt: debt ? assetAmountToYi(debt.value, debt.label) : 0,
      };
    })
    .filter((row): row is { name: string; cash: number; debt: number } => row != null)
    .sort((a, b) => b.cash - a.cash);
}
