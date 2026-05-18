import {
  Bar,
  BarChart,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ChartSpecLike } from "./types";

const AI_CHART_COLORS: Record<string, string> = {
  net_profit: "#10b981",
  revenue: "#3b82f6",
  growth: "#f59e0b",
  cost: "#ef4444",
  default: "#8b5cf6",
};

export function aiChartRowsFromSpec(spec: ChartSpecLike): Array<Record<string, string | number>> {
  const labels = spec?.xAxis?.data ?? [];
  const series = spec?.series ?? [];
  const rows: Array<Record<string, string | number>> = labels.map((label) => {
    const row: Record<string, string | number> = { name: label };
    series.forEach((s) => {
      const idx = labels.indexOf(label);
      row[s?.name ?? "value"] = (s?.data ?? [])[idx] ?? 0;
    });
    return row;
  });
  return rows;
}

export function aiSeriesColor(name: string, idx: number): string {
  const n = (name || "").toLowerCase();
  for (const key of Object.keys(AI_CHART_COLORS)) {
    if (n.includes(key)) return AI_CHART_COLORS[key];
  }
  return AI_CHART_COLORS.default || `hsl(${(idx * 137) % 360}, 60%, 55%)`;
}

export default function AiInlineChart({ spec }: { spec: Record<string, unknown> }) {
  const opt = spec as ChartSpecLike;
  const rows = aiChartRowsFromSpec(opt);
  const series = opt?.series ?? [];
  if (!rows.length || !series.length) return null;
  const isLine = series.every((s) => (s?.type || "bar").toLowerCase() === "line");
  return (
    <div className="mt-2 rounded border border-zinc-700 bg-zinc-900/60 p-2">
      <ResponsiveContainer width="100%" height={220}>
        {isLine ? (
          <LineChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <XAxis dataKey="name" tick={{ fontSize: 11 }} stroke="#71717a" />
            <YAxis tick={{ fontSize: 11 }} stroke="#71717a" />
            <RechartsTooltip contentStyle={{ backgroundColor: "#18181b", border: "1px solid #3f3f46" }} />
            <Legend />
            {series.map((s, idx) => {
              const name = String(s?.name || `系列${idx + 1}`);
              return (
                <Line key={`${name}-${idx}`} type="monotone" dataKey={name} stroke={aiSeriesColor(name, idx)} strokeWidth={2} dot={{ r: 2 }} />
              );
            })}
          </LineChart>
        ) : (
          <BarChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <XAxis dataKey="name" tick={{ fontSize: 11 }} stroke="#71717a" />
            <YAxis tick={{ fontSize: 11 }} stroke="#71717a" />
            <RechartsTooltip contentStyle={{ backgroundColor: "#18181b", border: "1px solid #3f3f46" }} />
            <Legend />
            {series.map((s, idx) => {
              const name = String(s?.name || `系列${idx + 1}`);
              return <Bar key={`${name}-${idx}`} dataKey={name} fill={aiSeriesColor(name, idx)} radius={[4, 4, 0, 0]} />;
            })}
          </BarChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}
