"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ChartPanel } from "./ChartPanel";
import { CompetitorChartTooltip, competitorBarTooltipProps } from "./CompetitorChartTooltip";
import { CHART_CARTESIAN_GRID, CHART_X_AXIS, CHART_Y_AXIS } from "../lib/competitor_chart_colors";

export type DivergingBarPoint = {
  name: string;
  delta: number;
  fill: string;
};

type Props = {
  title: string;
  data: DivergingBarPoint[];
  delayMs?: number;
  /** pct 模式：+1.2 pct；wan 模式：+123 万；yi 模式：轴以亿显示 */
  unit?: "pct" | "wan" | "yi";
  valueFormatter?: (v: number) => string;
};

function defaultFormatter(v: number, unit: Props["unit"]): string {
  if (unit === "pct") {
    const sign = v > 0 ? "+" : "";
    return `${sign}${v.toFixed(1)} 百分点`;
  }
  if (unit === "yi") {
    const sign = v > 0 ? "+" : "";
    return `${sign}${(v / 10000).toFixed(2)} 亿`;
  }
  const sign = v > 0 ? "+" : "";
  return `${sign}${Math.round(v).toLocaleString("zh-CN")} 万`;
}

export function DivergingBarPanel({
  title,
  data,
  delayMs = 80,
  unit = "wan",
  valueFormatter,
}: Props) {
  if (!data.length) return null;
  const h = Math.max(200, data.length * 32 + 48);
  const fmt = valueFormatter ?? ((v) => defaultFormatter(v, unit));

  return (
    <ChartPanel title={title} delayMs={delayMs} height="h-auto min-h-[200px]">
      <div style={{ height: h }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} layout="vertical" margin={{ left: 4, right: 12, top: 4, bottom: 4 }}>
            <CartesianGrid {...CHART_CARTESIAN_GRID} horizontal={false} />
            <XAxis
              type="number"
              {...CHART_X_AXIS}
              tickFormatter={(v) => {
                const n = Number(v);
                if (unit === "pct") return `${n > 0 ? "+" : ""}${n}`;
                if (unit === "yi") return `${n > 0 ? "+" : ""}${Math.round(n / 10000)}`;
                return `${n > 0 ? "+" : ""}${Math.round(n / 10000)}`;
              }}
              tick={{ fontSize: 9 }}
            />
            <YAxis
              type="category"
              dataKey="name"
              {...CHART_Y_AXIS}
              width={72}
              interval={0}
              tick={{ fontSize: 9 }}
            />
            <ReferenceLine x={0} stroke="#52525b" />
            <Tooltip
              {...competitorBarTooltipProps({
                content: <CompetitorChartTooltip valueFormatter={(v) => fmt(Number(v))} />,
              })}
            />
            <Bar dataKey="delta" name={title} radius={[0, 3, 3, 0]}>
              {data.map((d, i) => (
                <Cell key={i} fill={d.fill} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </ChartPanel>
  );
}
