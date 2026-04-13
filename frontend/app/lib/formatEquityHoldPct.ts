/**
 * 股权边「持股比例」展示：统一为百分比字符串，保留两位小数。
 * 优先使用数值字段 hold_pct（接口约定为 0~100）；仅有文本时再解析。
 */
export function formatEquityHoldPctDisplay(
  holdPct: number | null | undefined,
  holdPctText: string | null | undefined,
): string {
  if (holdPct != null && Number.isFinite(Number(holdPct))) {
    return `${Number(holdPct).toFixed(2)}%`;
  }
  const raw = String(holdPctText ?? "").trim();
  if (!raw) return "";
  const n = parseFloat(raw.replace(/%/g, "").replace(/,/g, "").trim());
  if (!Number.isFinite(n)) return raw;
  return `${n.toFixed(2)}%`;
}
