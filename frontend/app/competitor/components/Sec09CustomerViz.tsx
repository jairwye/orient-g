"use client";

import { useMemo } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ChartPanel } from "./ChartPanel";
import { CompetitorChartTooltip, competitorBarTooltipProps } from "./CompetitorChartTooltip";
import { BUSINESS_CHART_COLORS } from "../../lib/business_chart_colors";
import { CHART_CARTESIAN_GRID, CHART_X_AXIS, CHART_Y_AXIS, colorForCompany } from "../lib/competitor_chart_colors";
import { colToLabel, labelToCol } from "../lib/companies";
import { formatPctPoints, parseNum, toPercentPoints } from "../lib/format";
import type { CompetitorReportSnapshot, TableBlock } from "../lib/types";

const CUSTOMER_TYPES = ["前五客户", "前五供应商"] as const;

const CUSTOMER_COMPANY_ORDER = [
  "三七互娱",
  "完美世界",
  "掌趣科技",
  "塔人网络",
  "华清飞扬",
  "像素软件",
  "绿岸网络",
] as const;

function buildConcentrationRows(tables: TableBlock[]) {
  const rows: Array<{ company: string; type: string; name: string; pct: number }> = [];

  tables.forEach((table, ti) => {
    const companyLabel = CUSTOMER_COMPANY_ORDER[ti] ?? `公司${ti + 1}`;
    for (const row of table.rows) {
      const txType = String(row["往来类型"] ?? "");
      if (!CUSTOMER_TYPES.some((t) => txType.includes(t))) continue;
      const name = String(row["客商名称"] ?? "").trim() || txType;
      const raw = parseNum(row["占比"]);
      if (raw == null) continue;
      rows.push({
        company: companyLabel,
        type: txType.includes("供应商") ? "前五供应商" : "前五客户",
        name,
        pct: toPercentPoints(raw),
      });
    }
  });

  return rows.sort((a, b) => b.pct - a.pct).slice(0, 28);
}

/** 重要客商：前五客户/供应商集中度横条 */
export function Sec09CustomerViz({
  tables,
  snapshot,
  delayMs = 80,
}: {
  tables: TableBlock[];
  snapshot: CompetitorReportSnapshot;
  delayMs?: number;
}) {
  const chartData = useMemo(() => {
    return buildConcentrationRows(tables).map((d) => ({
      ...d,
      label: `${colToLabel(labelToCol(d.company) ?? d.company) || d.company} · ${d.name}`,
      fill: colorForCompany(labelToCol(d.company) ?? d.company, snapshot),
    }));
  }, [tables, snapshot]);

  if (!chartData.length) return null;

  const chartH = Math.max(240, chartData.length * 28 + 56);

  return (
    <ChartPanel title="前五客户/供应商集中度" delayMs={delayMs} height="h-auto min-h-[240px]">
      <div style={{ height: chartH }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData} layout="vertical" margin={{ left: 4, right: 16, top: 4, bottom: 4 }}>
            <CartesianGrid {...CHART_CARTESIAN_GRID} horizontal={false} />
            <XAxis type="number" domain={[0, "auto"]} {...CHART_X_AXIS} unit="%" tick={{ fontSize: 10 }} />
            <YAxis
              type="category"
              dataKey="label"
              {...CHART_Y_AXIS}
              width={168}
              interval={0}
              tick={{ fontSize: 9 }}
            />
            <Tooltip
              {...competitorBarTooltipProps({
                content: <CompetitorChartTooltip valueFormatter={(v) => formatPctPoints(v)} />,
              })}
            />
            <Bar dataKey="pct" name="占比" radius={[0, 3, 3, 0]}>
              {chartData.map((d, i) => (
                <Cell key={i} fill={d.fill ?? BUSINESS_CHART_COLORS.current} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </ChartPanel>
  );
}
