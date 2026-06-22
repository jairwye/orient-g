import { BUSINESS_CHART_COLORS } from "../../lib/business_chart_colors";
import type { CompetitorReportSnapshot } from "./types";
import { COMPANY_COLS, SUBJECT_COL } from "./companies";

/** UI spec §4 八公司色板 — 本公司独占经营蓝；其余明度更高、深色底可读 */
export const COMPANY_COLORS: Record<string, string> = {
  yycq: BUSINESS_CHART_COLORS.current,
  "37": "#818CF8",
  wm: "#FB7185",
  zq: "#4ADE80",
  tr: "#FBBF24",
  hq: "#A78BFA",
  xs: "#38BDF8",
  la: "#FB923C",
};

export const COMPANY_ORDER = ["yycq", "37", "wm", "zq", "tr", "hq", "xs", "la"] as const;

const LABEL_ALIASES: Record<string, string> = {
  YYCQ: "yycq",
  [SUBJECT_COL]: "yycq",
};
for (let i = 0; i < COMPANY_COLS.length - 1; i += 1) {
  const label = COMPANY_COLS[i + 1]!;
  const id = COMPANY_ORDER[i + 1];
  if (id) LABEL_ALIASES[label] = id;
}

export function resolveCompanyId(name: string, snapshot?: CompetitorReportSnapshot): string | null {
  const key = name.trim();
  if (LABEL_ALIASES[key]) return LABEL_ALIASES[key];
  const fromSnap = snapshot?.companies.find((c) => c.label === key || c.short === key || c.id === key);
  if (fromSnap) return fromSnap.id;
  const hit = COMPANY_ORDER.find((id) => key.includes(id) || false);
  return hit ?? null;
}

export function colorForCompany(
  idOrLabel: string,
  snapshot?: CompetitorReportSnapshot,
  fallbackIndex = 0,
): string {
  const id =
    COMPANY_COLORS[idOrLabel]
      ? idOrLabel
      : resolveCompanyId(idOrLabel, snapshot) ??
        snapshot?.companies.find((c) => c.label === idOrLabel || c.short === idOrLabel)?.id;
  if (id && COMPANY_COLORS[id]) return COMPANY_COLORS[id];
  const palette = Object.values(COMPANY_COLORS);
  return palette[fallbackIndex % palette.length];
}

/** 同一公司色板上的深浅档，用于区分产品类型等子系列 */
export function shadeCompanyColor(baseHex: string, level: number): string {
  const hex = baseHex.replace("#", "");
  if (hex.length !== 6) return baseHex;
  const r = parseInt(hex.slice(0, 2), 16);
  const g = parseInt(hex.slice(2, 4), 16);
  const b = parseInt(hex.slice(4, 6), 16);
  const mix = Math.min(Math.max(level, 0), 5) * 0.14;
  const blend = (c: number) => Math.round(c + (255 - c) * mix * 0.35 - c * mix * 0.25);
  const clamp = (n: number) => Math.min(255, Math.max(40, n));
  return `#${clamp(blend(r)).toString(16).padStart(2, "0")}${clamp(blend(g)).toString(16).padStart(2, "0")}${clamp(blend(b)).toString(16).padStart(2, "0")}`;
}

export function chartOpacity(companyLabel: string, highlight: string | null, snapshot?: CompetitorReportSnapshot): number {
  if (!highlight || highlight === "__all__") return 1;
  return companyLabel === highlight || resolveCompanyId(companyLabel, snapshot) === resolveCompanyId(highlight, snapshot)
    ? 1
    : 0.15;
}

/** 与 BusinessDashboard 对齐的坐标轴 / 网格 / Tooltip 样式 */
export const CHART_AXIS_TICK = { fill: "#a1a1aa", fontSize: 12 };

export const CHART_X_AXIS = {
  tick: CHART_AXIS_TICK,
  axisLine: { stroke: "#3f3f46" },
  tickLine: false,
} as const;

export const CHART_Y_AXIS = {
  tick: CHART_AXIS_TICK,
  axisLine: false,
  tickLine: false,
  tickMargin: 0,
  width: 52,
} as const;

export const CHART_GRID_STROKE = "#27272a";

export const CHART_CARTESIAN_GRID = {
  stroke: CHART_GRID_STROKE,
  strokeDasharray: "3 3",
} as const;

/** 柱状图 hover 高亮（与 BusinessDashboard 一致） */
export const CHART_BAR_CURSOR = {
  fill: "rgba(39,39,42,0.35)",
  stroke: "rgba(63,63,70,0.8)",
  strokeWidth: 1,
} as const;

/** 饼图/散点图：禁用柱状 cursor，避免 hover 区域异常 */
export const CHART_NO_CURSOR = false as const;

export const CHART_SCATTER_CURSOR = {
  strokeDasharray: "4 4",
  stroke: "#52525b",
  strokeWidth: 1,
} as const;

/** @deprecated 请用 CompetitorChartTooltip 组件 */
export const CHART_TOOLTIP_STYLE = {
  background: "#18181b",
  border: "1px solid #3f3f46",
  fontSize: 12,
  borderRadius: 6,
} as const;
