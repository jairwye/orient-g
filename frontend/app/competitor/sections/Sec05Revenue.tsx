"use client";

import { useMemo } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ChartCarousel, type ChartCarouselSlide } from "../components/ChartCarousel";
import { ChapterPanel } from "../components/ChapterPanel";
import { CompetitorChartTooltip, competitorBarTooltipProps } from "../components/CompetitorChartTooltip";
import { NarrativesFromSection } from "../components/NarrativeBlock";
import { BUSINESS_CHART_COLORS } from "../../lib/business_chart_colors";
import {
  CHART_CARTESIAN_GRID,
  CHART_X_AXIS,
  CHART_Y_AXIS,
  colorForCompany,
  shadeCompanyColor,
} from "../lib/competitor_chart_colors";
import { CL, FK } from "../lib/field_keys";
import { formatPctPoints, parseNum } from "../lib/format";
import { subTitleForSnap } from "../lib/navigation";
import { getTable } from "../lib/selectors";
import { type SectionProps } from "../lib/section_ui";

const REV_SHARE = "\u6536\u5165\u5360\u6bd4";
const MARGIN_CHANGE = "\u6bdb\u5229\u7387\u53d8\u52a8";

/** 移动类收入口径归一（图例合并、同色） */
const MOBILE_GAME_CANONICAL = "\u79fb\u52a8\u6e38\u620f";
const MOBILE_GAME_ALIASES = new Set([
  MOBILE_GAME_CANONICAL,
  "\u624b\u673a\u6e38\u620f",
  "\u79fb\u52a8\u7f51\u7edc\u6e38\u620f",
  "\u79fb\u52a8\u7ec8\u7aef\u6e38\u620f",
]);

/** 网页类收入口径归一（网页游戏 / 互联网页面游戏 同色） */
const WEB_GAME_CANONICAL = "\u7f51\u9875\u6e38\u620f";
const WEB_GAME_ALIASES = new Set([WEB_GAME_CANONICAL, "\u4e92\u8054\u7f51\u9875\u9762\u6e38\u620f"]);

/** 归一后产品类型色 */
const PRODUCT_TYPE_COLORS: Record<string, string> = {
  [MOBILE_GAME_CANONICAL]: BUSINESS_CHART_COLORS.current,
  "\u5ba2\u6237\u7aef\u6e38\u620f": BUSINESS_CHART_COLORS.actual,
  "PC/\u4e3b\u673a\u6e38\u620f": "#34d399",
  [WEB_GAME_CANONICAL]: "#a78bfa",
  "\u7535\u89c6\u5267\u53ca\u9662\u7ebf": "#f472b6",
  "\u6e38\u620f\u76f8\u5173": "#fbbf24",
  "\u5176\u4ed6": "#71717a",
  "\u5176\u4ed6/\u5f71\u89c6": "#78716c",
};

const FALLBACK_PRODUCT_COLORS = [
  BUSINESS_CHART_COLORS.current,
  BUSINESS_CHART_COLORS.actual,
  BUSINESS_CHART_COLORS.lastYear,
  "#71717a",
  "#d97706",
  "#0891b2",
  "#a78bfa",
  "#f472b6",
];

/** 图例展示顺序 */
const PRODUCT_TYPE_ORDER = [
  MOBILE_GAME_CANONICAL,
  "\u5ba2\u6237\u7aef\u6e38\u620f",
  "PC/\u4e3b\u673a\u6e38\u620f",
  WEB_GAME_CANONICAL,
  "\u7535\u89c6\u5267\u53ca\u9662\u7ebf",
  "\u6e38\u620f\u76f8\u5173",
  "\u5176\u4ed6",
  "\u5176\u4ed6/\u5f71\u89c6",
];

type ProductRow = Record<string, string | number | null>;

function companyLabel(raw: string): string {
  return raw === "YYCQ" ? FK.yycqLabel : raw;
}

function normalizeProductType(raw: string): string {
  const t = raw.trim();
  if (MOBILE_GAME_ALIASES.has(t)) return MOBILE_GAME_CANONICAL;
  if (WEB_GAME_ALIASES.has(t)) return WEB_GAME_CANONICAL;
  return t;
}

function normalizeShare(raw: number): number {
  return Math.abs(raw) <= 1 ? raw * 100 : raw;
}

function normalizeMargin(raw: number): number {
  return Math.abs(raw) <= 1 ? raw * 100 : raw;
}

function parseMarginChangePct(v: string | number | null | undefined): number | null {
  if (v == null || v === "") return null;
  return parseNum(String(v).replace(/pct/gi, ""));
}

function formatMarginChangePct(v: number): string {
  const sign = v > 0 ? "+" : "";
  return `${sign}${v.toFixed(1)}pct`;
}

function colorForProductType(type: string, index: number): string {
  return PRODUCT_TYPE_COLORS[type] ?? FALLBACK_PRODUCT_COLORS[index % FALLBACK_PRODUCT_COLORS.length];
}

function sortProductTypes(types: Iterable<string>): string[] {
  const set = new Set(types);
  const ordered = PRODUCT_TYPE_ORDER.filter((t) => set.has(t));
  const rest = [...set].filter((t) => !PRODUCT_TYPE_ORDER.includes(t)).sort((a, b) => a.localeCompare(b, "zh-CN"));
  return [...ordered, ...rest];
}

function buildRevenueMix(rows: ProductRow[]) {
  const productTypes = new Set<string>();
  const byCompany = new Map<string, { name: string; company: string; segments: Record<string, number> }>();

  for (const row of rows) {
    const company = String(row[FK.company] ?? "");
    const productType = normalizeProductType(String(row[FK.productType] ?? ""));
    const shareRaw = parseNum(row[REV_SHARE]);
    if (!company || !productType || shareRaw == null) continue;
    productTypes.add(productType);
    if (!byCompany.has(company)) {
      byCompany.set(company, { name: companyLabel(company), company, segments: {} });
    }
    const share = normalizeShare(shareRaw);
    byCompany.get(company)!.segments[productType] = (byCompany.get(company)!.segments[productType] ?? 0) + share;
  }

  const types = sortProductTypes(productTypes);
  const data = [...byCompany.values()].map(({ name, company, segments }) => {
    const item: Record<string, string | number> = { name, company };
    for (const t of types) item[t] = segments[t] ?? 0;
    return item;
  });

  return { types, data };
}

function buildProductMarginRows(rows: ProductRow[], snapshot: SectionProps["snapshot"]) {
  const byCompany = new Map<string, ProductRow[]>();
  for (const row of rows) {
    const company = String(row[FK.company] ?? "");
    if (!company) continue;
    if (!byCompany.has(company)) byCompany.set(company, []);
    byCompany.get(company)!.push(row);
  }

  const result: Array<{
    label: string;
    company: string;
    productType: string;
    margin: number;
    fill: string;
  }> = [];

  for (const [company, items] of byCompany) {
    const base = colorForCompany(company, snapshot);
    items.forEach((row, idx) => {
      const productType = normalizeProductType(String(row[FK.productType] ?? ""));
      const marginRaw = parseNum(row[FK.grossMargin]);
      if (!productType || marginRaw == null) return;
      result.push({
        label: `${companyLabel(company)} \u00b7 ${productType}`,
        company,
        productType,
        margin: normalizeMargin(marginRaw),
        fill: shadeCompanyColor(base, idx),
      });
    });
  }

  return result.sort((a, b) => a.company.localeCompare(b.company, "zh-CN") || b.margin - a.margin);
}

function buildMarginChangeRows(rows: ProductRow[], snapshot: SectionProps["snapshot"]) {
  const byCompany = new Map<string, ProductRow[]>();
  for (const row of rows) {
    const company = String(row[FK.company] ?? "");
    if (!company) continue;
    if (!byCompany.has(company)) byCompany.set(company, []);
    byCompany.get(company)!.push(row);
  }

  const result: Array<{
    label: string;
    company: string;
    productType: string;
    change: number;
    fill: string;
  }> = [];

  for (const [company, items] of byCompany) {
    const base = colorForCompany(company, snapshot);
    items.forEach((row, idx) => {
      const productType = normalizeProductType(String(row[FK.productType] ?? ""));
      const change = parseMarginChangePct(row[MARGIN_CHANGE]);
      if (!productType || change == null) return;
      result.push({
        label: `${companyLabel(company)} \u00b7 ${productType}`,
        company,
        productType,
        change,
        fill: shadeCompanyColor(base, idx),
      });
    });
  }

  return result.sort((a, b) => a.company.localeCompare(b.company, "zh-CN") || b.change - a.change);
}

export function Sec05Revenue({ snapshot }: SectionProps) {
  const sec05 = snapshot.sections.find((s) => s.id === "sec-05");
  const product = getTable(snapshot, "sec-05-1");

  const { types, data: mixData } = useMemo(
    () => buildRevenueMix(product?.rows ?? []),
    [product?.rows],
  );
  const marginRows = useMemo(
    () => buildProductMarginRows(product?.rows ?? [], snapshot),
    [product?.rows, snapshot],
  );
  const marginChangeRows = useMemo(
    () => buildMarginChangeRows(product?.rows ?? [], snapshot),
    [product?.rows, snapshot],
  );

  const rowCount = Math.max(marginRows.length, marginChangeRows.length, mixData.length, 1);
  const chartHeightPx = Math.max(360, rowCount * 28 + 48);
  const carouselHeightPx = chartHeightPx + 100;
  const carouselHeight = `h-[min(${carouselHeightPx}px,72vh)]`;
  const marginYAxisWidth = 168;

  const slides: ChartCarouselSlide[] = [
    {
      id: "mix",
      title: CL.productRevenueShare,
      content: (
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={mixData}
            layout="vertical"
            margin={{ left: 4, right: 24, top: 4, bottom: 28 }}
            barCategoryGap="14%"
          >
            <CartesianGrid {...CHART_CARTESIAN_GRID} horizontal={false} />
            <XAxis type="number" domain={[0, 100]} {...CHART_X_AXIS} unit="%" tick={{ fontSize: 10 }} />
            <YAxis type="category" dataKey="name" {...CHART_Y_AXIS} width={72} tick={{ fontSize: 10 }} />
            <Tooltip {...competitorBarTooltipProps({ content: <CompetitorChartTooltip valueFormatter={(v) => formatPctPoints(v)} /> })} />
            <Legend wrapperStyle={{ fontSize: 10 }} verticalAlign="bottom" />
            {types.map((type, typeIdx) => (
              <Bar
                key={type}
                dataKey={type}
                name={type}
                stackId="mix"
                fill={colorForProductType(type, typeIdx)}
                fillOpacity={0.92}
              >
                <LabelList
                  dataKey={type}
                  position="center"
                  formatter={(v: number) => (v >= 8 ? formatPctPoints(v) : "")}
                  fill="#f4f4f5"
                  fontSize={9}
                  style={{ pointerEvents: "none" }}
                />
              </Bar>
            ))}
          </BarChart>
        </ResponsiveContainer>
      ),
    },
    {
      id: "margin-by-type",
      title: CL.productMarginByType,
      content: (
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={marginRows}
            layout="vertical"
            margin={{ left: 8, right: 12, top: 4, bottom: 8 }}
            barCategoryGap="10%"
          >
            <CartesianGrid {...CHART_CARTESIAN_GRID} horizontal={false} />
            <XAxis type="number" domain={[0, 100]} {...CHART_X_AXIS} unit="%" tick={{ fontSize: 10 }} />
            <YAxis
              type="category"
              dataKey="label"
              {...CHART_Y_AXIS}
              width={marginYAxisWidth}
              tick={{ fontSize: 9 }}
              interval={0}
            />
            <Tooltip {...competitorBarTooltipProps({ content: <CompetitorChartTooltip valueFormatter={(v) => formatPctPoints(v)} /> })} />
            <Bar dataKey="margin" name={CL.margin} radius={[0, 3, 3, 0]}>
              {marginRows.map((d, i) => (
                <Cell key={i} fill={d.fill} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      ),
    },
    {
      id: "margin-change",
      title: CL.productMarginChange,
      content: (
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={marginChangeRows}
            layout="vertical"
            margin={{ left: 8, right: 12, top: 4, bottom: 8 }}
            barCategoryGap="10%"
          >
            <CartesianGrid {...CHART_CARTESIAN_GRID} horizontal={false} />
            <XAxis
              type="number"
              {...CHART_X_AXIS}
              tickFormatter={(v) => formatMarginChangePct(v)}
              tick={{ fontSize: 10 }}
            />
            <YAxis
              type="category"
              dataKey="label"
              {...CHART_Y_AXIS}
              width={marginYAxisWidth}
              tick={{ fontSize: 9 }}
              interval={0}
            />
            <Tooltip
              {...competitorBarTooltipProps({
                content: <CompetitorChartTooltip valueFormatter={(v) => formatMarginChangePct(Number(v))} />,
              })}
            />
            <ReferenceLine x={0} stroke="#52525b" />
            <Bar dataKey="change" name={MARGIN_CHANGE} radius={[0, 3, 3, 0]}>
              {marginChangeRows.map((d, i) => (
                <Cell key={i} fill={d.change >= 0 ? BUSINESS_CHART_COLORS.actual : "#ef4444"} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      ),
    },
  ];

  return (
    <ChapterPanel
      sectionId="sec-05"
      slides={[
        {
          id: "sec-05-a",
          title: subTitleForSnap("sec-05-a"),
          content: (
            <>
              <ChartCarousel
                slides={slides}
                autoMs={8000}
                autoStartDelayMs={3000}
                hideArrows
                height={carouselHeight}
                chartHeightPx={chartHeightPx}
              />
              <div className="mt-3 text-sm leading-relaxed text-zinc-400">
                <NarrativesFromSection
                  blocks={sec05?.blocks ?? []}
                  anchor="sec-05-1"
                  plain
                  stripAnalysisPrefix
                />
              </div>
            </>
          ),
        },
      ]}
    />
  );
}
