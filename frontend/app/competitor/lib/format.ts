/** 四舍五入保留两位小数 */
export function round2(n: number): number {
  return Math.round(n * 100) / 100;
}

export function parseNum(v: string | number | null | undefined): number | null {
  if (v == null || v === "") return null;
  if (typeof v === "number") return Number.isFinite(v) ? v : null;
  const s = String(v).trim();
  if (s === "—" || s === "-" || s === "N/A") return null;
  const pct = s.endsWith("%");
  let inner = s.replace(/,/g, "").replace(/，/g, "");
  if (pct) inner = inner.slice(0, -1);
  if (inner.endsWith("x") || inner.endsWith("X")) {
    const n = parseFloat(inner.slice(0, -1));
    return Number.isFinite(n) ? n : null;
  }
  if (inner.includes("亿")) {
    const n = parseFloat(inner.replace(/[^\d.-]/g, ""));
    return Number.isFinite(n) ? n * 10000 : null;
  }
  const n = parseFloat(inner.replace(/[^\d.-]/g, ""));
  if (!Number.isFinite(n)) return null;
  if (pct && Math.abs(n) > 1) return n / 100;
  return n;
}

export function parseScore(v: string | number | null | undefined): number | null {
  if (v == null) return null;
  if (typeof v === "number") return v;
  const m = String(v).match(/([\d.]+)/);
  return m ? parseFloat(m[1]) : null;
}

/** 将比率或百分点统一为「百分比数值」（如 8.5 表示 8.5%） */
export function toPercentPoints(n: number): number {
  const abs = Math.abs(n);
  if (abs === 0) return 0;
  if (abs <= 1) return round2(n * 100);
  if (abs <= 100) return round2(n);
  if (abs <= 10) return round2(n * 100);
  return round2(n);
}

export function isPercentColumnKey(key: string): boolean {
  const k = key.trim();
  if (k.includes("同比")) return true;
  if (k.includes("变动") && !k.includes("人数") && !k.includes("金额")) return true;
  if (k.includes("增减率")) return true;
  if (k.includes("幅度")) return true;
  if (k.includes("(pct)")) return true;
  if (/ROE/i.test(k)) return true;
  if (k.includes("毛利率") || k.includes("费用率") || k.includes("占比")) return true;
  if (k.includes("经营CF/净利") || k.includes("CF/净利")) return true;
  if (k.includes("净利率") || k.includes("收益率")) return true;
  if (k.endsWith("率") && !k.includes("增长")) return true;
  return false;
}

const PRESERVE_TEXT = /家|亿|扭亏|减亏|约|—|-/;

export function formatDecimal2(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  const r = round2(n);
  if (Number.isInteger(r)) {
    return r.toLocaleString("zh-CN");
  }
  return r.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function formatPct(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return `${toPercentPoints(n).toFixed(2)}%`;
}

export function formatYiWan(n: number | null | undefined, unit = "万"): string {
  if (n == null || !Number.isFinite(n)) return "—";
  const r = round2(n);
  if (unit === "亿" && Math.abs(r) >= 10000) return `${round2(r / 10000).toFixed(2)} 亿`;
  if (Math.abs(r) >= 10000) return `${round2(r / 10000).toFixed(2)} 亿`;
  return `${formatDecimal2(r)} ${unit}`;
}

export function formatScore(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return round2(n).toFixed(2);
}

/** 表格/卡片单元格：同比等百分数列、其余数值两位小数 */
export function formatTableCell(
  columnKey: string,
  val: string | number | null | undefined,
): string {
  if (val == null || val === "") return "—";
  if (typeof val === "string") {
    const t = val.trim();
    if (!t || t === "—" || t === "-") return "—";
    if (PRESERVE_TEXT.test(t) && !/^-?\d/.test(t)) return t;
    if (t.endsWith("%") && isPercentColumnKey(columnKey)) {
      const n = parseNum(t);
      return n != null ? formatPct(n) : t;
    }
    if (t.includes("亿") || t.includes("约")) return t;
    const parsed = parseNum(t);
    if (parsed == null) return t;
    if (isPercentColumnKey(columnKey)) return formatPct(parsed);
    return formatDecimal2(parsed);
  }
  if (isPercentColumnKey(columnKey)) return formatPct(val);
  return formatDecimal2(val);
}

/** 千分位 + 两位小数 */
export function formatDisplayNumber(val: string | number | null | undefined): string {
  if (val == null || val === "") return "—";
  if (typeof val === "string") {
    const t = val.trim();
    if (PRESERVE_TEXT.test(t) && !/^-?\d/.test(t)) return t;
  }
  const n = typeof val === "number" ? val : parseNum(val);
  if (n == null) return String(val);
  return formatDecimal2(n);
}

/** 图表 tooltip：已是 0–100 的百分点 */
export function formatPctPoints(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return `${round2(n).toFixed(2)}%`;
}

/** sec-06-3 偿债表：按行指标名格式化（参照蓝本） */
const SOLVENCY_PERCENT_METRICS = ["资产负债率", "货币资金/总资产", "应收账款/流动资产", "有息负债率"] as const;
const SOLVENCY_TIMES_METRICS = ["权益乘数", "应收账款周转率", "总资产周转率"] as const;

export function formatSolvencyMetricValue(
  metric: string,
  val: string | number | null | undefined,
): string {
  if (val == null || val === "") return "—";
  const n = parseNum(val);
  if (n == null) return String(val);
  const m = metric.trim();
  if (SOLVENCY_PERCENT_METRICS.some((k) => m === k || m.includes(k))) return formatPct(n);
  if (m.includes("净现金")) return `${formatDecimal2(n)} 亿`;
  if (SOLVENCY_TIMES_METRICS.some((k) => m === k || m.includes(k))) return `${formatDecimal2(n)}x`;
  return formatDecimal2(n);
}
