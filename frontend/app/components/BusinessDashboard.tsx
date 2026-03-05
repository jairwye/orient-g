"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { TrendingDown, TrendingUp } from "lucide-react";
import {
  Area,
  Bar,
  BarChart,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const PROFIT_BAR_GRADIENT_ID = "profitBarGradient";
const PROFIT_COMPARE_LAST_YEAR_GRADIENT_ID = "profitCompareLastYearGradient";
const PROFIT_COMPARE_CURRENT_GRADIENT_ID = "profitCompareCurrentGradient";
const FLOW_ACTUAL_GRADIENT_ID = "flowActualGradient";
const FLOW_UNFINISHED_GRADIENT_ID = "flowUnfinishedGradient";

const chartHeight = 280;
const PROFIT_TREND_BAR_SIZE = 40;
const FLOW_BAR_SIZE = 40;
const PROFIT_COMPARE_BAR_SIZE = 30;
/** 左列两格总高（2*图表高度 + 两段标题/内边距/间距），用于右列流水图对齐 */
const leftColumnTotalHeight = 2 * chartHeight + 136;

const DEFAULT_STATS = [
  { title: "流水", value: "—", desc: "万元", completionRatio: "—" as string },
  { title: "利润", value: "—", desc: "万元", lastYearValue: "—" as string, changePercent: "—" as string },
  { title: "资金", value: "—", desc: "万元", overseas: "—" as string, overseasRatio: "—" as string },
];

type Overview = {
  stats: {
    title: string;
    value: string;
    desc: string;
    completionRatio?: string;
    lastYearValue?: string;
    changePercent?: string;
    overseas?: string;
    overseasRatio?: string;
  }[];
  profitTrend: { labels: string[]; currentYear: number[]; previousYear: number[] };
  flowCompare: { labels: string[]; actual: number[]; target: number[] };
  profitCompare: { labels: string[]; currentYear: number[]; lastYear: number[] };
};

const fetchOverview = () =>
  fetch("/api/business/overview", { cache: "no-store" })
    .then((r) => r.json())
    .then((data) => data as Overview)
    .catch(() => null);

const CHART_COLORS = {
  current: "#818cf8",
  previous: "#3f3f46",
  actual: "#22c55e",
  target: "#3f3f46",
  lastYear: "#52525b",
};

/** 数字展示：千分位、保留两位小数；非数字（如 "—"）原样返回 */
function formatNumber(val: string | number): string {
  if (val === "" || val === null || val === undefined) return "—";
  const n = typeof val === "number" ? val : Number(val);
  if (Number.isNaN(n)) return String(val);
  return n.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

/** Recharts 坐标轴数字格式化 */
const formatTick = (value: number) => formatNumber(value);

/** Recharts 通用 Tooltip：数值千分位 + 两位小数；本年_面积 不展示，本年_线 展示为「本年」 */
function ChartTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: { name: string; value: number; dataKey: string }[];
  label?: string;
}) {
  if (!active || !payload?.length || label == null) return null;
  const items = payload
    .filter((entry) => entry.dataKey !== "本年_面积")
    .map((entry) => ({
      ...entry,
      displayName: entry.dataKey === "本年_线" ? "本年" : entry.name,
    }));
  return (
    <div className="rounded-md border border-zinc-600 bg-zinc-900 px-3 py-2 shadow-lg">
      <p className="mb-1.5 text-xs font-medium text-zinc-400">{label}</p>
      <ul className="space-y-0.5 text-sm tabular-nums text-zinc-100">
        {items.map((entry) => (
          <li key={entry.dataKey}>
            {entry.displayName}: {formatNumber(entry.value)}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** 流水堆叠图 Tooltip：展示实际、目标、完成率 */
function FlowTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: { payload: { 实际: number; 目标: number } }[];
  label?: string;
}) {
  if (!active || !payload?.length || label == null) return null;
  const { 实际, 目标 } = payload[0].payload;
  const ratio =
    目标 != null && 目标 > 0
      ? `${((实际 / 目标) * 100).toFixed(1)}%`
      : "—";
  return (
    <div className="rounded-md border border-zinc-600 bg-zinc-900 px-3 py-2 shadow-lg">
      <p className="mb-1.5 text-xs font-medium text-zinc-400">{label}</p>
      <ul className="space-y-0.5 text-sm tabular-nums text-zinc-100">
        <li>实际: {formatNumber(实际)}</li>
        <li>目标: {formatNumber(目标)}</li>
        <li>完成率: {ratio}</li>
      </ul>
    </div>
  );
}

export default function BusinessDashboard() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [loading, setLoading] = useState(true);

  const loadOverview = useCallback(() => {
    setLoading(true);
    fetchOverview()
      .then((data) => setOverview(data))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    loadOverview();
  }, [loadOverview]);

  const stats = overview?.stats ?? DEFAULT_STATS;
  const pt = overview?.profitTrend ?? { labels: [], currentYear: [], previousYear: [] };
  const fc = overview?.flowCompare ?? { labels: [], actual: [], target: [] };
  const pc = overview?.profitCompare ?? { labels: [], currentYear: [], lastYear: [] };

  const profitTrendData = useMemo(
    () =>
      pt.labels.map((name, i) => {
        const v = pt.currentYear[i] ?? 0;
        return {
          name,
          往年: pt.previousYear[i] ?? 0,
          本年_线: v,
          本年_面积: v,
        };
      }),
    [pt]
  );
  const flowCompareData = useMemo(
    () =>
      fc.labels.map((name, i) => {
        const 实际 = Number(fc.actual[i]) || 0;
        const 目标 = Number(fc.target[i]) || 0;
        return {
          name,
          实际,
          目标,
          未完成: Math.max(0, 目标 - 实际),
        };
      }),
    [fc]
  );
  const profitCompareData = useMemo(
    () =>
      pc.labels.map((name, i) => ({
        name,
        本年: pc.currentYear[i] ?? 0,
        去年: pc.lastYear[i] ?? 0,
      })),
    [pc]
  );

  const hasProfitTrend = profitTrendData.length > 0;
  const hasFlowCompare = flowCompareData.length > 0;
  const hasProfitCompare = profitCompareData.length > 0;

  const totalFlowTarget = useMemo(
    () => fc.target.reduce((a, b) => a + b, 0),
    [fc.target]
  );

  return (
    <div className="p-6 md:p-8">
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-100">经营数据</h1>
        <p className="text-right text-sm text-zinc-500 md:max-w-sm">数据由财务于后台上传 Excel 表（流水、利润、资金与趋势）</p>
      </div>

      {loading && (
        <p className="mb-4 text-sm text-zinc-500">加载中…</p>
      )}

      <div className="mb-8 grid gap-4 sm:grid-cols-3">
        {stats.map((card, index) => {
          const isFlowCard = index === 0;
          const isProfitCard = index === 1;
          const isFundCard = index === 2;
          const changePercent = isProfitCard ? card.changePercent : undefined;
          const hasChangePercent = changePercent != null && changePercent !== "—";
          const changeNum = hasChangePercent ? Number(changePercent.replace("%", "")) : 0;
          const isPositive = !Number.isNaN(changeNum) && changeNum > 0;
          const isNegative = !Number.isNaN(changeNum) && changeNum < 0;
          const changeDisplay = hasChangePercent
            ? (changePercent.includes("%") ? changePercent : `${changePercent}%`)
            : "";
          const hasOverseasRatio = isFundCard && card.overseasRatio != null && card.overseasRatio !== "—";
          const overseasRatioDisplay = hasOverseasRatio
            ? (card.overseasRatio!.includes("%") ? card.overseasRatio : `${card.overseasRatio}%`)
            : "";
          return (
            <div
              key={card.title}
              className="relative min-h-[160px] rounded-lg border border-zinc-800 bg-zinc-900/50 p-5"
            >
              {isFlowCard && card.completionRatio != null && card.completionRatio !== "—" && (
                <div className="absolute right-3 top-3 rounded border border-zinc-800 bg-zinc-950 px-2 py-1 text-xs font-medium tabular-nums text-zinc-300">
                  完成比例 {card.completionRatio.includes("%") ? card.completionRatio : `${card.completionRatio}%`}
                </div>
              )}
              {isProfitCard && hasChangePercent && (
                <div className="absolute right-3 top-3 flex items-center gap-1 rounded border border-zinc-800 bg-zinc-950 px-2 py-1 text-xs font-medium tabular-nums text-zinc-300">
                  {isPositive && <TrendingUp className="h-3.5 w-3.5" style={{ color: CHART_COLORS.current }} />}
                  {isNegative && <TrendingDown className="h-3.5 w-3.5" style={{ color: CHART_COLORS.current }} />}
                  {changeDisplay}
                </div>
              )}
              {isFundCard && hasOverseasRatio && (
                <div className="absolute right-3 top-3 rounded border border-zinc-800 bg-zinc-950 px-2 py-1 text-xs font-medium tabular-nums text-zinc-300">
                  海外占比 {overseasRatioDisplay}
                </div>
              )}
              <p className="text-sm font-medium text-zinc-400">
                {isFlowCard ? "本年流水" : isProfitCard ? "本年利润" : isFundCard ? "资金总额" : card.title}
              </p>
              <p className="mt-2 font-bold tabular-nums text-zinc-100 text-5xl tracking-tight">
                {formatNumber(card.value)}
              </p>
              {isFlowCard && totalFlowTarget > 0 && (
                <p className="mt-3 text-lg text-zinc-500">
                  目标 {formatNumber(totalFlowTarget)} {card.desc}
                </p>
              )}
              {isProfitCard && card.lastYearValue != null && card.lastYearValue !== "—" && (
                <p className="mt-3 text-lg text-zinc-500">
                  去年同期 {formatNumber(card.lastYearValue)} {card.desc}
                </p>
              )}
              {isFundCard && card.overseas != null && card.overseas !== "—" && (
                <p className="mt-3 text-lg text-zinc-500">
                  海外 {formatNumber(card.overseas)} {card.desc}
                </p>
              )}
              {isFlowCard && totalFlowTarget <= 0 && (
                <p className="mt-3 text-lg text-zinc-500">{card.desc}</p>
              )}
              {isProfitCard && (card.lastYearValue == null || card.lastYearValue === "—") && (
                <p className="mt-3 text-lg text-zinc-500">{card.desc}</p>
              )}
              {isFundCard && (card.overseas == null || card.overseas === "—") && (
                <p className="mt-3 text-lg text-zinc-500">{card.desc}</p>
              )}
              {!isFlowCard && !isProfitCard && !isFundCard && (
                <p className="mt-3 text-lg text-zinc-500">{card.desc}</p>
              )}
            </div>
          );
        })}
      </div>

      <div className="grid gap-6 sm:grid-cols-[1.12fr_0.88fr]">
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
          <h3 className="mb-3 text-sm font-medium text-zinc-300">利润（本年趋势与往年）</h3>
          {hasProfitTrend ? (
            <ResponsiveContainer width="100%" height={chartHeight}>
              <ComposedChart data={profitTrendData} margin={{ top: 8, right: 8, left: -8, bottom: 0 }}>
                <defs>
                  <linearGradient id={PROFIT_BAR_GRADIENT_ID} x1="0" y1="1" x2="0" y2="0">
                    <stop offset="0%" stopColor="#fafafa" stopOpacity="0.25" />
                    <stop offset="100%" stopColor="#fafafa" stopOpacity="1" />
                  </linearGradient>
                </defs>
                <XAxis dataKey="name" tick={{ fill: "#a1a1aa", fontSize: 12 }} axisLine={{ stroke: "#3f3f46" }} tickLine={false} />
                <YAxis
                  width={40}
                  tick={{ fill: "#a1a1aa", fontSize: 12 }}
                  axisLine={false}
                  tickLine={false}
                  tickFormatter={formatTick}
                  tickMargin={0}
                />
                <Tooltip content={<ChartTooltip />} />
                <Legend verticalAlign="top" align="right" wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="往年" fill={`url(#${PROFIT_BAR_GRADIENT_ID})`} radius={[4, 4, 0, 0]} barSize={PROFIT_TREND_BAR_SIZE} />
                <Area type="monotone" dataKey="本年_面积" fill={CHART_COLORS.current} fillOpacity={0.2} stroke="transparent" legendType="none" />
                <Line type="monotone" dataKey="本年_线" name="本年" stroke={CHART_COLORS.current} strokeWidth={2} dot={{ fill: CHART_COLORS.current }} />
              </ComposedChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex items-center justify-center text-sm text-zinc-500" style={{ height: chartHeight }}>暂无数据，请上传 Excel</div>
          )}
        </div>
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 sm:row-span-2 flex flex-col" style={{ minHeight: leftColumnTotalHeight }}>
          <h3 className="mb-3 text-sm font-medium text-zinc-300">流水（实际 vs 目标）</h3>
          {hasFlowCompare ? (
            <div className="flex-1 min-h-0">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={flowCompareData} layout="vertical" margin={{ top: 8, right: 8, left: 8, bottom: 8 }}>
                  <defs>
                    <linearGradient id={FLOW_UNFINISHED_GRADIENT_ID} x1="0" y1="0" x2="1" y2="0">
                      <stop offset="0%" stopColor="#ffffff" stopOpacity="0.25" />
                      <stop offset="100%" stopColor="#ffffff" stopOpacity="0.85" />
                    </linearGradient>
                    <linearGradient id={FLOW_ACTUAL_GRADIENT_ID} x1="0" y1="0" x2="1" y2="0">
                      <stop offset="0%" stopColor={CHART_COLORS.current} stopOpacity="0.25" />
                      <stop offset="100%" stopColor={CHART_COLORS.current} stopOpacity="1" />
                    </linearGradient>
                  </defs>
                  <XAxis type="number" domain={[0, "auto"]} tick={{ fill: "#a1a1aa", fontSize: 12 }} axisLine={{ stroke: "#3f3f46" }} tickLine={false} tickFormatter={formatTick} />
                  <YAxis type="category" dataKey="name" width={80} tick={{ fill: "#a1a1aa", fontSize: 12 }} axisLine={{ stroke: "#3f3f46" }} tickLine={false} />
                  <Tooltip
                    content={<FlowTooltip />}
                    cursor={{ fill: "rgba(39,39,42,0.35)", stroke: "rgba(63,63,70,0.8)", strokeWidth: 1 }}
                  />
                  <Legend verticalAlign="top" align="right" wrapperStyle={{ fontSize: 12 }} />
                  <Bar dataKey="实际" name="实际" stackId="flow" fill={`url(#${FLOW_ACTUAL_GRADIENT_ID})`} radius={[4, 0, 0, 4]} barSize={FLOW_BAR_SIZE} />
                  <Bar dataKey="未完成" name="未完成" stackId="flow" fill={`url(#${FLOW_UNFINISHED_GRADIENT_ID})`} radius={[0, 4, 4, 0]} barSize={FLOW_BAR_SIZE} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="flex-1 flex items-center justify-center text-sm text-zinc-500">暂无数据，请上传 Excel</div>
          )}
        </div>
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
          <h3 className="mb-3 text-sm font-medium text-zinc-300">项目利润（本年 vs 去年）</h3>
          {hasProfitCompare ? (
            <ResponsiveContainer width="100%" height={chartHeight}>
              <BarChart data={profitCompareData} margin={{ top: 8, right: 8, left: -8, bottom: 0 }}>
                <defs>
                  <linearGradient id={PROFIT_COMPARE_LAST_YEAR_GRADIENT_ID} x1="0" y1="1" x2="0" y2="0">
                    <stop offset="0%" stopColor="#ffffff" stopOpacity="0.25" />
                    <stop offset="100%" stopColor="#ffffff" stopOpacity="0.85" />
                  </linearGradient>
                  <linearGradient id={PROFIT_COMPARE_CURRENT_GRADIENT_ID} x1="0" y1="1" x2="0" y2="0">
                    <stop offset="0%" stopColor={CHART_COLORS.current} stopOpacity="0.25" />
                    <stop offset="100%" stopColor={CHART_COLORS.current} stopOpacity="1" />
                  </linearGradient>
                </defs>
                <XAxis dataKey="name" tick={{ fill: "#a1a1aa", fontSize: 12 }} axisLine={{ stroke: "#3f3f46" }} tickLine={false} />
                <YAxis
                  width={40}
                  tick={{ fill: "#a1a1aa", fontSize: 12 }}
                  axisLine={false}
                  tickLine={false}
                  tickFormatter={formatTick}
                  tickMargin={0}
                />
                <Tooltip
                  content={<ChartTooltip />}
                  cursor={{ fill: "rgba(39,39,42,0.35)", stroke: "rgba(63,63,70,0.8)", strokeWidth: 1 }}
                />
                <Legend verticalAlign="top" align="right" wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="本年" fill={`url(#${PROFIT_COMPARE_CURRENT_GRADIENT_ID})`} radius={[4, 4, 0, 0]} barSize={PROFIT_COMPARE_BAR_SIZE} />
                <Bar dataKey="去年" fill={`url(#${PROFIT_COMPARE_LAST_YEAR_GRADIENT_ID})`} radius={[4, 4, 0, 0]} barSize={PROFIT_COMPARE_BAR_SIZE} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex items-center justify-center text-sm text-zinc-500" style={{ height: chartHeight }}>暂无数据，请上传 Excel</div>
          )}
        </div>
      </div>
    </div>
  );
}
