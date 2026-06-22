import { formatTableCell, formatTableCellForRow, isPercentColumnKey } from "./format";

/** 版号/ISBN 占位或脱敏 → 视为无有效版号 */
export function isIncompleteLicense(val: unknown): boolean {
  const s = String(val ?? "").trim();
  if (!s || s === "—" || s === "-") return true;
  if (/不适用/.test(s)) return true;
  if (/\*{2,}/.test(s)) return true;
  if (/ISBN[\s\d-]*\*+/i.test(s)) return true;
  return false;
}

const TEXT_HEADERS =
  /名称|项目|游戏|公司|竞企|产品类型|品类|备注|期间|性质|方案|运营|收费|渠道|客商|公司名称|分发|投资|变动原因|变更日|产品类型/;

/** sec-09 明细表：保留代号/游戏名原文；版号脱敏隐藏；费比/持股用百分数 */
export function sec09FormatCell(
  header: string,
  val: string | number | null | undefined,
  row?: Record<string, string | number | null>,
): string {
  const h = header.trim();
  if (h.includes("版号") || h.includes("ISBN")) {
    if (isIncompleteLicense(val)) return "—";
    return String(val).trim();
  }
  if (TEXT_HEADERS.test(h)) {
    if (val == null || val === "") return "—";
    return String(val);
  }
  if (isPercentColumnKey(h) || h.includes("费比") || h.includes("持股比例") || h.includes("股权变动")) {
    return formatTableCell(h, val);
  }
  return formatTableCellForRow(h, val, row);
}

/** 主要游戏：版号列暂不展示 */
export function stripLicenseColumn(
  headers: string[],
  rows: Record<string, string | number | null>[],
): { headers: string[]; rows: Record<string, string | number | null>[] } {
  const col = headers.find((h) => h.includes("版号") || h.includes("ISBN"));
  if (!col) return { headers, rows };
  const nextHeaders = headers.filter((h) => h !== col);
  const nextRows = rows.map((row) => {
    const copy = { ...row };
    delete copy[col];
    return copy;
  });
  return { headers: nextHeaders, rows: nextRows };
}

/** @deprecated 使用 stripLicenseColumn */
export function stripIncompleteLicenseColumn(
  headers: string[],
  rows: Record<string, string | number | null>[],
): { headers: string[]; rows: Record<string, string | number | null>[] } {
  return stripLicenseColumn(headers, rows);
}
