import type { ReactNode } from "react";
import { companyDisplayLabel } from "./companies";
import { FK } from "./field_keys";
import { formatTableCell, parseNum } from "./format";
import type { CompetitorReportSnapshot } from "./types";

export const SEC05_REV_SHARE = "\u6536\u5165\u5360\u6bd4";
export const SEC05_COST_SHARE = "\u6210\u672c\u5360\u6bd4";
export const SEC05_MARGIN_CHANGE = "\u6bdb\u5229\u7387\u53d8\u52a8";
export const SEC05_REV_DELTA_AMT = "\u6536\u5165\u589e\u51cf\u989d";
export const SEC05_REV_DELTA_RATE = "\u6536\u5165\u589e\u51cf\u7387";
export const SEC05_COST_DELTA_AMT = "\u6210\u672c\u589e\u51cf\u989d";
export const SEC05_COST_DELTA_RATE = "\u6210\u672c\u589e\u51cf\u7387";

export type Sec05ProductRow = Record<string, string | number | null>;

const TEXT_HEADERS = new Set<string>([FK.company, FK.productType]);

/** 蓝本新版 8 列：无「成本占比 / 收入增减额 / …」，列已对齐，无需还原 */
export function isSec05CompactHeader(headers: string[]): boolean {
  return headers.length > 0 && !headers.includes(SEC05_COST_SHARE);
}

function hasRevenueDeltaAmount(row: Sec05ProductRow): boolean {
  const v = row[SEC05_REV_DELTA_AMT];
  if (v == null || v === "" || v === "—" || v === "-") return false;
  const t = String(v).trim();
  // 压缩行常把「毛利率变动」错位到收入增减额列（如 -3.6pct）
  if (/pct/i.test(t)) return false;
  return true;
}

function pickMisalignedMarginChange(row: Sec05ProductRow): string | number | null | undefined {
  const amt = row[SEC05_REV_DELTA_AMT];
  if (typeof amt === "string" && /pct/i.test(amt.trim())) return amt;
  const rate = row[SEC05_REV_DELTA_RATE];
  if (typeof rate === "string" && /pct/i.test(String(rate).trim())) return rate;
  return row[SEC05_MARGIN_CHANGE];
}

/**
 * 蓝本 sec-05-1：
 * - **紧凑 8 列**（收入/占比/成本/毛利率/收入增减率/毛利率变动）：直接引用；
 * - **宽 12 列**：本公司等完整行；其余公司压缩行需还原 毛利率 / 收入增减率 / 毛利率变动。
 */
export function normalizeSec05ProductRow(
  row: Sec05ProductRow,
  headers?: string[],
): Sec05ProductRow {
  if (headers && isSec05CompactHeader(headers)) return row;
  if (hasRevenueDeltaAmount(row)) return row;

  const rateSlot = row[SEC05_REV_DELTA_RATE];
  if (typeof rateSlot === "string" && /pct/i.test(rateSlot)) {
    return {
      ...row,
      [FK.grossMargin]: row[SEC05_COST_SHARE],
      [SEC05_REV_DELTA_RATE]: row[FK.grossMargin],
      [SEC05_MARGIN_CHANGE]: rateSlot,
      [SEC05_COST_SHARE]: null,
    };
  }

  const costShare = row[SEC05_COST_SHARE];
  const marginSlot = row[FK.grossMargin];
  if (costShare != null && marginSlot != null && marginSlot !== "") {
    return {
      ...row,
      [FK.grossMargin]: costShare,
      [SEC05_REV_DELTA_RATE]: marginSlot,
      [SEC05_MARGIN_CHANGE]: pickMisalignedMarginChange(row) ?? null,
      [SEC05_COST_SHARE]: null,
      [SEC05_REV_DELTA_AMT]: null,
    };
  }

  return row;
}

export function normalizeSec05ProductRows(
  rows: Sec05ProductRow[],
  headers?: string[],
): Sec05ProductRow[] {
  return rows.map((row) => normalizeSec05ProductRow(row, headers));
}

function preserveDeltaText(val: string | number | null | undefined): string {
  if (val == null || val === "") return "—";
  const t = String(val).trim();
  if (t === "—" || t === "-") return "—";
  if (/万/.test(t)) return t.replace(/\s+/g, "");
  return formatTableCell("", val);
}

export function formatSec05ProductCell(
  header: string,
  val: string | number | null | undefined,
  snapshot: CompetitorReportSnapshot,
): ReactNode {
  const h = header.trim();
  if (h === FK.company) {
    const raw = val == null ? "" : String(val);
    return raw ? companyDisplayLabel(raw, snapshot) : "—";
  }
  if (TEXT_HEADERS.has(h)) {
    return val == null || val === "" ? "—" : String(val);
  }
  if (h === SEC05_REV_DELTA_AMT || h === SEC05_COST_DELTA_AMT) {
    return preserveDeltaText(val);
  }
  if (h === SEC05_MARGIN_CHANGE) {
    if (val == null || val === "") return "—";
    const t = String(val).trim();
    if (t === "—" || t === "-") return "—";
    return t.replace(/\s+/g, "");
  }
  return formatTableCell(h, val);
}

export function parseSec05MarginChangePct(v: string | number | null | undefined): number | null {
  if (v == null || v === "") return null;
  const t = String(v).trim();
  if (t === "—" || t === "-") return null;
  return parseNum(t.replace(/pct/gi, ""));
}

/**
 * sec-05 收入占比/毛利率等：蓝本与 snapshot 已是百分点（71.3=71.3%，0.7=0.7%）。
 * 勿对 (0,1) 再 ×100，否则 0.7% 会被错成 70% 导致堆叠图超 100%。
 */
export function sec05PercentPoints(n: number): number {
  return n;
}
