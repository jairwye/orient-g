/** 四舍五入保留两位小数 */
export function round2(n: number): number {
  return Math.round(n * 100) / 100;
}

export function parseNum(v: string | number | null | undefined): number | null {
  if (v == null || v === "") return null;
  if (typeof v === "number") return Number.isFinite(v) ? v : null;
  const s = String(v).trim();
  if (s === "—" || s === "-" || s === "N/A") return null;
  if (/[\u4e00-\u9fff]/.test(s)) {
    if (/^\d{4}年/.test(s)) {
      // 保留「2024年…」类，不在此解析
    } else if (!/亿|万|约|家|扭亏|减亏/.test(s)) {
      return null;
    }
  }
  if (/[a-zA-Z]/.test(s) && !/^[+-]?\d/.test(s)) return null;
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
  const n = parseFloat(inner.replace(/[^\d.+-]/g, ""));
  if (!Number.isFinite(n)) return null;
  // 带 % 的蓝本数字即百分点，直接引用（如 -214.6%、41.4%）
  if (pct) return n;
  return n;
}

export function parseScore(v: string | number | null | undefined): number | null {
  if (v == null) return null;
  if (typeof v === "number") return v;
  const m = String(v).match(/([\d.]+)/);
  return m ? parseFloat(m[1]) : null;
}

/** sec-08-2 经营现金流/净利：蓝本 1.22 表示 122%，0.414 表示 41.4%；亦可能已是 41.4% */
export function cfProfitRatioToPercentPoints(n: number): number {
  const abs = Math.abs(n);
  if (abs === 0) return 0;
  if (abs <= 3) return round2(n * 100);
  if (abs <= 200) return round2(n);
  return round2(n);
}

function fractionalDecimalPlaces(n: number): number {
  const s = String(n);
  const dot = s.indexOf(".");
  if (dot === -1) return 0;
  return s.length - dot - 1;
}

/**
 * 将 snapshot 数值统一为百分点（41.4 表示 41.4%）。
 * 兼容旧版 /100 存储（如 2.146→214.6%）；新版与蓝本带 % 单元格为直接百分点（5.0→5.0%）。
 */
export function toPercentPoints(n: number): number {
  const abs = Math.abs(n);
  if (abs === 0) return 0;
  if (abs < 1) return round2(n * 100);
  const scaled = round2(n * 100);
  // 旧 snapshot 大百分比被 /100：须三位及以上小数；避免 5.0/4.9 等客商占比被误 ×100
  if (abs < 5 && Math.abs(scaled) >= 50 && fractionalDecimalPlaces(n) >= 3) return scaled;
  return round2(n);
}

/** 蓝本「占比/持股/费比」等列已是百分点，与 sec-05 一致直接引用 */
export function sharePercentPoints(n: number): number {
  return round2(n);
}

/** 占比/费比/持股列：蓝本数值即百分点，不做 <1 小数比例换算 */
export function isSharePercentColumnKey(key: string): boolean {
  const k = key.trim();
  return k.includes("占比") || k.includes("费比") || k.includes("持股比例");
}

export function isDateColumnKey(key: string): boolean {
  return /变更日|日期/.test(key.trim());
}

/** 蓝本日期字面量原样展示（2025/5/22、2025年、2025-06-13） */
export function blueprintDateLiteral(val: string | number | null | undefined): string | null {
  if (typeof val !== "string") return null;
  const t = val.trim();
  if (!t || t === "—" || t === "-") return null;
  if (/^\d{4}年/.test(t)) return t;
  if (/^\d{4}[\/\-.]\d{1,2}([\/\-.]\d{1,2})?$/.test(t)) return t;
  return null;
}

/** 按列类型将 snapshot 数值格式化为百分数字符串 */
export function formatPercentForCell(
  columnKey: string,
  n: number | null | undefined,
  metric?: string,
): string {
  if (n == null || !Number.isFinite(n)) return "—";
  const useShare =
    isSharePercentColumnKey(columnKey) || (metric != null && isSharePercentColumnKey(metric));
  const points = useShare ? sharePercentPoints(n) : toPercentPoints(n);
  return formatPercentFromPoints(points);
}

/** 百分点 → 展示串：与蓝本一致，不补尾零 */
export function formatPercentFromPoints(points: number): string {
  if (!Number.isFinite(points)) return "—";
  const r = round2(points);
  if (Number.isInteger(r)) return `${r.toLocaleString("zh-CN")}%`;
  const formatted = r.toLocaleString("zh-CN", { minimumFractionDigits: 0, maximumFractionDigits: 2 });
  return `${formatted}%`;
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
  if (k.includes("经营CF/净利") || k.includes("经营现金流/净利") || k.includes("CF/净利")) return true;
  if (k.includes("净利率") || k.includes("收益率")) return true;
  if (k.includes("费比") || k.includes("持股比例") || k.includes("股权变动")) return true;
  if (k.includes("收现比")) return true;
  if (k.endsWith("率") && !k.includes("增长") && !/周转|乘数/.test(k)) return true;
  return false;
}

/** 宽表行指标（指标/项目列）是否应按百分数展示 */
export function isPercentMetricLabel(metric: string): boolean {
  const m = metric.trim();
  if (!m) return false;
  if (/综合ROI|^ROI/i.test(m)) return false;
  if (/周转率|权益乘数|乘数/.test(m)) return false;
  if (isPercentColumnKey(m)) return true;
  if (m.includes("占比") || m.includes("比率") || m.includes("费比") || m.includes("收现比")) return true;
  if (m.includes("/") && /费|CF|净利|销售|资产|负债|现金|收入/.test(m)) return true;
  return false;
}

/** 宽表行指标是否应为倍数（x） */
export function isTimesMetricLabel(metric: string): boolean {
  const m = metric.trim();
  return /综合ROI|ROI/i.test(m) || /权益乘数/.test(m) || /周转率/.test(m);
}

const ROW_METRIC_KEYS = ["指标", "项目", "科目", "事项", "metric"] as const;

export function rowMetricLabel(
  row?: Record<string, string | number | null>,
  labelKey?: string,
): string {
  if (!row) return "";
  if (labelKey && row[labelKey] != null) return String(row[labelKey]).trim();
  for (const k of ROW_METRIC_KEYS) {
    if (row[k] != null && String(row[k]).trim()) return String(row[k]).trim();
  }
  return "";
}

const PRESERVE_TEXT = /家|亿|扭亏|减亏|约|—|-/;

/** 蓝本单元格含 % 时原样展示（+18.0%、93.0% 等，不走 toPercentPoints 重算） */
export function blueprintPercentLiteral(val: string | number | null | undefined): string | null {
  if (typeof val !== "string") return null;
  const t = val.trim().replace(/\s+/g, "");
  if (!t || t === "—" || t === "-") return null;
  if (t.endsWith("%")) return t;
  return null;
}

/** 蓝本倍数 x 字面量原样展示（12.3x） */
export function blueprintTimesLiteral(val: string | number | null | undefined): string | null {
  if (typeof val !== "string") return null;
  const t = val.trim().replace(/\s+/g, "");
  if (/^-?[\d,]+(\.\d+)?[xX]$/.test(t)) return t;
  return null;
}

/** 蓝本中的纯数字串（保留小数位，如 8.8、1,234.5） */
function blueprintNumericLiteral(raw: string): string | null {
  const t = raw.trim();
  if (!t || t === "—" || t === "-") return null;
  const compact = t.replace(/\s+/g, "").replace(/，/g, ",");
  if (/^-?[\d,]+(\.\d+)?$/.test(compact)) return t.replace(/\s+/g, "");
  if (/^-?[\d,]+(\.\d+)?[xX]$/.test(compact)) return t.replace(/\s+/g, "");
  return null;
}

export function formatDecimal2(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  const r = round2(n);
  if (Number.isInteger(r) && r >= 1990 && r <= 2099) {
    return String(r);
  }
  if (Number.isInteger(r)) {
    return r.toLocaleString("zh-CN");
  }
  // 不补尾零：8.8 而非 8.80（与蓝本小数位一致）
  return r.toLocaleString("zh-CN", { minimumFractionDigits: 0, maximumFractionDigits: 2 });
}

export function formatPct(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return formatPercentFromPoints(toPercentPoints(n));
}

export function formatYiWan(n: number | null | undefined, unit = "万"): string {
  if (n == null || !Number.isFinite(n)) return "—";
  const r = round2(n);
  if (unit === "亿" && Math.abs(r) >= 10000) return `${formatDecimal2(r / 10000)} 亿`;
  if (Math.abs(r) >= 10000) return `${formatDecimal2(r / 10000)} 亿`;
  return `${formatDecimal2(r)} ${unit}`;
}

export function formatScore(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return formatDecimal2(n);
}

/** 表格/卡片单元格：同比等百分数列、其余数值两位小数 */
export function formatTableCell(
  columnKey: string,
  val: string | number | null | undefined,
): string {
  if (val == null || val === "") return "—";
  const pctLiteral = blueprintPercentLiteral(val);
  if (pctLiteral) return pctLiteral;
  const timesLiteral = blueprintTimesLiteral(val);
  if (timesLiteral) return timesLiteral;
  const col = columnKey.trim();
  if (isDateColumnKey(col)) {
    const dateLiteral = blueprintDateLiteral(val);
    if (dateLiteral) return dateLiteral;
    if (typeof val === "string" && val.trim()) return val.trim();
  }
  if (
    col.includes("期间") ||
    col.includes("方案") ||
    col.includes("备注") ||
    col.includes("性质") ||
    isDateColumnKey(col) ||
    /名称|项目|游戏|版号|ISBN|品类|渠道|运营|收费|客商|公司名称/.test(col)
  ) {
    return String(val).trim() || "—";
  }
  if (typeof val === "string") {
    const t = val.trim();
    if (!t || t === "—" || t === "-") return "—";
    if (PRESERVE_TEXT.test(t) && !/^-?\d/.test(t)) return t;
    if (/^\d{4}年/.test(t)) return t;
    if (blueprintDateLiteral(t)) return t;
    if (t.endsWith("%")) {
      return t.replace(/\s+/g, "");
    }
    if (!isPercentColumnKey(columnKey)) {
      const numericLiteral = blueprintNumericLiteral(t);
      if (numericLiteral != null) {
        const n = parseNum(numericLiteral);
        if (n != null) return formatDecimal2(n);
        return numericLiteral;
      }
    }
    if (t.includes("亿") || t.includes("约")) return t;
    const parsed = parseNum(t);
    if (parsed == null) return t;
    if (isPercentColumnKey(columnKey)) return formatPercentForCell(columnKey, parsed);
    return formatDecimal2(parsed);
  }
  if (isPercentColumnKey(columnKey)) return formatPercentForCell(columnKey, val);
  return formatDecimal2(val);
}

/** 宽表：结合行指标（广告/销售费用等）决定 % / x / 数值格式 */
export function formatTableCellForRow(
  columnKey: string,
  val: string | number | null | undefined,
  row?: Record<string, string | number | null>,
  rowLabelKey?: string,
): string {
  const pctLiteral = blueprintPercentLiteral(val);
  if (pctLiteral) return pctLiteral;
  const timesLiteral = blueprintTimesLiteral(val);
  if (timesLiteral) return timesLiteral;

  const metric = rowMetricLabel(row, rowLabelKey);
  if (metric && isTimesMetricLabel(metric)) {
    if (val == null || val === "") return "—";
    if (typeof val === "string") {
      const t = val.trim();
      if (t.endsWith("x") || t.endsWith("X")) return t.replace(/\s+/g, "");
    }
    const n = typeof val === "number" ? val : parseNum(val);
    if (n != null) return `${formatDecimal2(n)}x`;
    return String(val);
  }
  if (metric && isPercentMetricLabel(metric)) {
    if (val == null || val === "") return "—";
    const n = typeof val === "number" ? val : parseNum(val);
    if (n != null) return formatPercentForCell(columnKey, n, metric);
    return formatTableCell(columnKey, val);
  }
  return formatTableCell(columnKey, val);
}

/** 千分位；小数位与数值一致，不补尾零 */
export function formatDisplayNumber(val: string | number | null | undefined): string {
  if (val == null || val === "") return "—";
  if (typeof val === "string") {
    const t = val.trim();
    if (PRESERVE_TEXT.test(t) && !/^-?\d/.test(t)) return t;
    const numericLiteral = blueprintNumericLiteral(t);
    if (numericLiteral != null) {
      const n = parseNum(numericLiteral);
      if (n != null) return formatDecimal2(n);
      return numericLiteral;
    }
  }
  const n = typeof val === "number" ? val : parseNum(val);
  if (n == null) return String(val);
  return formatDecimal2(n);
}

/** 图表 tooltip：已是百分点（41.4 表示 41.4%） */
export function formatPctPoints(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return formatPercentFromPoints(n);
}

/** sec-06-3 偿债表：按行指标名格式化（参照蓝本） */
const SOLVENCY_PERCENT_METRICS = ["资产负债率", "货币资金/总资产", "应收账款/流动资产", "有息负债率"] as const;
const SOLVENCY_TIMES_METRICS = ["权益乘数", "应收账款周转率", "总资产周转率"] as const;

export function formatSolvencyMetricValue(
  metric: string,
  val: string | number | null | undefined,
): string {
  if (val == null || val === "") return "—";
  if (typeof val === "string" && val.trim().endsWith("%")) {
    return val.trim().replace(/\s+/g, "");
  }
  const n = parseNum(val);
  if (n == null) return String(val);
  const m = metric.trim();
  if (SOLVENCY_PERCENT_METRICS.some((k) => m === k || m.includes(k))) return formatPct(n);
  if (m.includes("净现金")) return `${formatDecimal2(n)} 亿`;
  if (SOLVENCY_TIMES_METRICS.some((k) => m === k || m.includes(k))) return `${formatDecimal2(n)}x`;
  return formatDecimal2(n);
}
