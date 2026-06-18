"use client";

import { useMemo } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ChartPanel } from "./ChartPanel";
import { ChartCarousel } from "./ChartCarousel";
import { CompetitorChartTooltip, competitorBarTooltipProps } from "./CompetitorChartTooltip";
import { BUSINESS_CHART_COLORS } from "../../lib/business_chart_colors";
import { CHART_CARTESIAN_GRID, CHART_X_AXIS, CHART_Y_AXIS, colorForCompany } from "../lib/competitor_chart_colors";
import { colToLabel, labelToCol } from "../lib/companies";
import { CL } from "../lib/field_keys";
import { formatPctPoints } from "../lib/format";
import type { CompetitorReportSnapshot, TableBlock } from "../lib/types";

const COMPANY_KEYS = ["竞企名称", "公司"] as const;
const PROJECT_NAME_KEYS = ["项目名称"] as const;
const GAME_NAME_KEYS = ["游戏名称"] as const;
const STAGE_KEY = "项目进展";
const REGION_KEY = "发行地区";
const CATEGORY_KEY = "品类";

function fillDownCompany(rows: Record<string, string | number | null>[]): Array<Record<string, string | number | null>> {
  let last = "";
  return rows.map((row) => {
    const raw = String(row[COMPANY_KEYS[0]] ?? row[COMPANY_KEYS[1]] ?? "").trim();
    if (raw && raw !== "—" && raw !== "-") last = raw;
    return { ...row, __company: last };
  });
}

function classifyPipelineStage(progress: string): "dev" | "test" | "live" | "stop" | "other" {
  const p = progress.trim();
  if (!p || p === "—") return "other";
  if (/停止|终止|注销/.test(p)) return "stop";
  if (/已上线|上线|公测|运营|持续运营/.test(p)) return "live";
  if (/测试/.test(p)) return "test";
  if (/研发|在研|开发/.test(p)) return "dev";
  return "dev";
}

const STAGE_LABEL: Record<ReturnType<typeof classifyPipelineStage>, string> = {
  dev: "研发/在研",
  test: "测试中",
  live: "已上线/公测",
  stop: "已终止",
  other: "其他",
};

const STAGE_COLOR: Record<ReturnType<typeof classifyPipelineStage>, string> = {
  dev: BUSINESS_CHART_COLORS.current,
  test: "#d97706",
  live: BUSINESS_CHART_COLORS.actual,
  stop: "#71717a",
  other: "#52525b",
};

export function RndPipelineViz({
  table,
  delayMs = 80,
}: {
  table: TableBlock;
  delayMs?: number;
}) {
  const { chartData, stages } = useMemo(() => {
    const stageSet = new Set<ReturnType<typeof classifyPipelineStage>>();
    const byCompany = new Map<string, Record<string, string | number>>();

    for (const row of fillDownCompany(table.rows)) {
      const company = String(row.__company ?? "").trim();
      const name = String(row[PROJECT_NAME_KEYS[0]] ?? "").trim();
      if (!company || !name || name === "—") continue;
      const stage = classifyPipelineStage(String(row[STAGE_KEY] ?? ""));
      stageSet.add(stage);
      const label = colToLabel(labelToCol(company) ?? company) || company;
      if (!byCompany.has(label)) byCompany.set(label, { name: label });
      const bucket = byCompany.get(label)!;
      const key = STAGE_LABEL[stage];
      bucket[key] = (Number(bucket[key]) || 0) + 1;
    }

    const stages = (["dev", "test", "live", "stop", "other"] as const).filter((s) => stageSet.has(s));
    const chartData = [...byCompany.values()].sort((a, b) => {
      const ta = stages.reduce((n, s) => n + (Number(a[STAGE_LABEL[s]]) || 0), 0);
      const tb = stages.reduce((n, s) => n + (Number(b[STAGE_LABEL[s]]) || 0), 0);
      return tb - ta;
    });

    return { chartData, stages };
  }, [table.rows]);

  if (!chartData.length) return null;

  const chartH = Math.max(220, chartData.length * 36 + 56);

  return (
    <ChartPanel title={CL.pipelineStageMix} delayMs={delayMs} height="h-auto min-h-[220px]">
      <div style={{ height: chartH }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData} layout="vertical" margin={{ left: 4, right: 16, top: 4, bottom: 4 }}>
            <CartesianGrid {...CHART_CARTESIAN_GRID} horizontal={false} />
            <XAxis type="number" allowDecimals={false} {...CHART_X_AXIS} tick={{ fontSize: 10 }} />
            <YAxis type="category" dataKey="name" {...CHART_Y_AXIS} width={80} interval={0} tick={{ fontSize: 10 }} />
            <Tooltip {...competitorBarTooltipProps({ content: <CompetitorChartTooltip valueFormatter={(v) => `${v} 项`} /> })} />
            <Legend wrapperStyle={{ fontSize: 10 }} />
            {stages.map((stage) => (
              <Bar
                key={stage}
                dataKey={STAGE_LABEL[stage]}
                name={STAGE_LABEL[stage]}
                stackId="pipe"
                fill={STAGE_COLOR[stage]}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
    </ChartPanel>
  );
}

function normalizeRegion(raw: string): string {
  const t = raw.trim();
  if (!t || t === "—") return "未标注";
  if (t.includes("全球")) return "全球";
  if (t.includes("境外")) return "境外";
  if (t.includes("中国大陆") || t.includes("境内")) return "境内";
  return t;
}

function normalizeCategory(raw: string): string {
  const t = raw.trim();
  if (!t || t === "—") return "未标注";
  if (t.length > 12) return `${t.slice(0, 11)}…`;
  return t;
}

function buildPctStackRows(
  map: Map<string, Record<string, string | number>>,
  keys: string[],
): Array<Record<string, string | number>> {
  return [...map.values()]
    .map((row) => {
      const total = keys.reduce((n, k) => n + (Number(row[k]) || 0), 0);
      if (total <= 0) return null;
      const pctRow: Record<string, string | number> = { name: row.name, __total: total };
      for (const k of keys) {
        const c = Number(row[k]) || 0;
        pctRow[k] = Math.round((c / total) * 1000) / 10;
      }
      return pctRow;
    })
    .filter(Boolean)
    .sort((a, b) => (Number(b!.__total) || 0) - (Number(a!.__total) || 0)) as Array<
    Record<string, string | number>
  >;
}

export function OperatingProductsViz({
  table,
  snapshot,
  delayMs = 80,
}: {
  table: TableBlock;
  snapshot: CompetitorReportSnapshot;
  delayMs?: number;
}) {
  const { countData, categoryData, categories, regionData, regions } = useMemo(() => {
    const counts = new Map<string, number>();
    const categoryMap = new Map<string, Record<string, string | number>>();
    const categorySet = new Set<string>();
    const regionMap = new Map<string, Record<string, string | number>>();
    const regionSet = new Set<string>();

    for (const row of fillDownCompany(table.rows)) {
      const company = String(row.__company ?? "").trim();
      const game = String(row[GAME_NAME_KEYS[0]] ?? row[PROJECT_NAME_KEYS[0]] ?? "").trim();
      if (!company || !game || game === "—") continue;

      const label = colToLabel(labelToCol(company) ?? company) || company;
      counts.set(label, (counts.get(label) ?? 0) + 1);

      const category = normalizeCategory(String(row[CATEGORY_KEY] ?? ""));
      categorySet.add(category);
      if (!categoryMap.has(label)) categoryMap.set(label, { name: label });
      const catBucket = categoryMap.get(label)!;
      catBucket[category] = (Number(catBucket[category]) || 0) + 1;

      const region = normalizeRegion(String(row[REGION_KEY] ?? ""));
      regionSet.add(region);
      if (!regionMap.has(label)) regionMap.set(label, { name: label });
      const regBucket = regionMap.get(label)!;
      regBucket[region] = (Number(regBucket[region]) || 0) + 1;
    }

    const categories = [...categorySet].sort((a, b) => a.localeCompare(b, "zh-CN"));
    const regions = [...regionSet].sort((a, b) => a.localeCompare(b, "zh-CN"));

    const countData = [...counts.entries()]
      .map(([name, value]) => ({
        name,
        value,
        fill: colorForCompany(labelToCol(name) ?? name, snapshot),
      }))
      .sort((a, b) => b.value - a.value);

    return {
      countData,
      categoryData: buildPctStackRows(categoryMap, categories),
      categories,
      regionData: buildPctStackRows(regionMap, regions),
      regions,
    };
  }, [table.rows, snapshot]);

  if (!countData.length) return null;

  const chartH = Math.max(260, countData.length * 38 + 72);
  const stackColors = [BUSINESS_CHART_COLORS.current, BUSINESS_CHART_COLORS.actual, "#d97706", "#71717a", "#52525b", "#3b82f6"];

  const countChart = (
    <div style={{ height: chartH }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={countData} layout="vertical" margin={{ left: 4, right: 16, top: 4, bottom: 4 }}>
          <CartesianGrid {...CHART_CARTESIAN_GRID} horizontal={false} />
          <XAxis type="number" allowDecimals={false} {...CHART_X_AXIS} tick={{ fontSize: 10 }} />
          <YAxis type="category" dataKey="name" {...CHART_Y_AXIS} width={88} interval={0} tick={{ fontSize: 10 }} />
          <Tooltip {...competitorBarTooltipProps({ content: <CompetitorChartTooltip valueFormatter={(v) => `${v} 款`} /> })} />
          <Bar dataKey="value" name={CL.productCountByCompany} radius={[0, 3, 3, 0]}>
            {countData.map((d, i) => (
              <Cell key={i} fill={d.fill} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );

  const stackChart = (
    keys: string[],
    data: Array<Record<string, string | number>>,
  ) => (
    <div style={{ height: chartH }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ left: 4, right: 16, top: 4, bottom: 28 }}>
          <CartesianGrid {...CHART_CARTESIAN_GRID} horizontal={false} />
          <XAxis type="number" domain={[0, 100]} {...CHART_X_AXIS} unit="%" tick={{ fontSize: 10 }} />
          <YAxis type="category" dataKey="name" {...CHART_Y_AXIS} width={88} interval={0} tick={{ fontSize: 10 }} />
          <Tooltip
            {...competitorBarTooltipProps({
              content: <CompetitorChartTooltip valueFormatter={(v) => formatPctPoints(v)} />,
            })}
          />
          <Legend wrapperStyle={{ fontSize: 10 }} verticalAlign="bottom" />
          {keys.map((key, i) => (
            <Bar key={key} dataKey={key} name={key} stackId="mix" fill={stackColors[i % stackColors.length]} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );

  const slides = [
    { id: "count", title: CL.productCountByCompany, content: countChart },
    ...(categoryData.length && categories.length
      ? [{ id: "category", title: CL.productCategoryMix, content: stackChart(categories, categoryData) }]
      : []),
    ...(regionData.length && regions.length
      ? [{ id: "region", title: CL.productRegionMix, content: stackChart(regions, regionData) }]
      : []),
  ];

  return (
    <div className="mt-5 sm:mt-6">
      <ChartCarousel slides={slides} chartHeightPx={chartH} autoStartDelayMs={delayMs + 2000} autoMs={7000} />
    </div>
  );
}
