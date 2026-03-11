"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Area,
  Brush,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

/** 与经营数据页一致的蓝色 */
const CHART_BLUE = "#2563eb";

/** 每隔 3 个数据点显示一个亮点：白圈蓝底 */
function DotEveryThird(props: { cx?: number; cy?: number; index?: number }) {
  const { cx, cy, index } = props;
  if (cx == null || cy == null || index == null || index % 3 !== 0) return null;
  return (
    <circle
      cx={cx}
      cy={cy}
      r={4}
      fill={CHART_BLUE}
      stroke="#fff"
      strokeWidth={2}
    />
  );
}

const DEFAULT_DAYS = 60;
const MIN_VISIBLE_DAYS = 7;
const WHEEL_ZOOM_FACTOR = 1.15;
const CURRENCY_LABELS: Record<"usd" | "eur" | "jpy", string> = {
  usd: "美元/人民币",
  eur: "欧元/人民币",
  jpy: "日元/人民币",
};

type HistoryPoint = { date: string; usd: number | null; eur: number | null; jpy: number | null };
type ChartPoint = { date: string; value: number | null };

function formatRate(v: number | null): string {
  if ( v == null || Number.isNaN(v) ) return "—";
  return v.toLocaleString("zh-CN", { minimumFractionDigits: 4, maximumFractionDigits: 4 });
}

type FetchStatus = { fetching: boolean; totalRecords: number; lastFilledDate: string | null };

export default function ExchangePage() {
  const [raw, setRaw] = useState<HistoryPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState<FetchStatus | null>(null);
  const [currency, setCurrency] = useState<"usd" | "eur" | "jpy">("usd");
  const [brushRange, setBrushRange] = useState<{ startIndex: number; endIndex: number } | null>(null);
  const [isPanning, setIsPanning] = useState(false);
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const brushContainerRef = useRef<HTMLDivElement>(null);
  const lastPanClientXRef = useRef<number>(0);

  const fetchHistory = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/exchange/history", { cache: "no-store" });
      const json = await res.json();
      const list: HistoryPoint[] = Array.isArray(json?.data) ? json.data : [];
      setRaw(list);
    } catch {
      setRaw([]);
    } finally {
      setLoading(false);
    }
  }, []);

  const dataKey = currency;
  const chartData: ChartPoint[] = useMemo(() => {
    return raw
      .filter((r) => r.date != null && r.date !== "")
      .map((r) => {
        const v = r[dataKey];
        const numVal = v != null && !Number.isNaN(v) ? v : null;
        return { date: String(r.date), value: numVal };
      });
  }, [raw, dataKey]);

  useEffect(() => {
    if (chartData.length > 0 && brushRange === null) {
      const end = chartData.length - 1;
      const start = Math.max(0, end - DEFAULT_DAYS + 1);
      setBrushRange({ startIndex: start, endIndex: end });
    }
  }, [chartData.length, brushRange]);

  const handleChartWheel = useCallback(
    (e: WheelEvent) => {
      if (chartData.length < 2 || brushRange == null || !chartContainerRef.current) return;
      const { startIndex, endIndex } = brushRange;
      const span = endIndex - startIndex + 1;
      const rect = chartContainerRef.current.getBoundingClientRect();
      const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
      const anchorIndex = startIndex + ratio * (span - 1);

      const delta = e.deltaY > 0 ? 1 : -1;
      const newSpan =
        delta < 0
          ? Math.max(MIN_VISIBLE_DAYS, Math.floor(span / WHEEL_ZOOM_FACTOR))
          : Math.min(chartData.length, Math.ceil(span * WHEEL_ZOOM_FACTOR));
      if (newSpan === span) return;

      let newStart = Math.round(anchorIndex - ratio * (newSpan - 1));
      let newEnd = newStart + newSpan - 1;
      if (newStart < 0) {
        newStart = 0;
        newEnd = Math.min(chartData.length - 1, newSpan - 1);
      } else if (newEnd >= chartData.length) {
        newEnd = chartData.length - 1;
        newStart = Math.max(0, newEnd - newSpan + 1);
      }
      setBrushRange({ startIndex: newStart, endIndex: newEnd });
    },
    [chartData.length, brushRange]
  );

  useEffect(() => {
    const el = chartContainerRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      handleChartWheel(e);
      e.preventDefault();
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [handleChartWheel]);

  const handlePanStart = useCallback(
    (e: React.MouseEvent) => {
      if (e.button !== 0) return;
      if (!brushRange || chartData.length <= 1) return;
      const span = brushRange.endIndex - brushRange.startIndex + 1;
      if (span >= chartData.length) return;
      if (brushContainerRef.current?.contains(e.nativeEvent.target as Node)) return;
      setIsPanning(true);
      lastPanClientXRef.current = e.clientX;
    },
    [brushRange, chartData.length]
  );

  useEffect(() => {
    if (!isPanning) return;
    const onMove = (e: MouseEvent) => {
      const deltaX = e.clientX - lastPanClientXRef.current;
      lastPanClientXRef.current = e.clientX;
      const width = chartContainerRef.current?.getBoundingClientRect().width ?? 300;
      setBrushRange((prev) => {
        if (!prev) return prev;
        const span = prev.endIndex - prev.startIndex + 1;
        const indexDelta = -(deltaX * span) / width;
        let newStart = Math.round(prev.startIndex + indexDelta);
        let newEnd = newStart + span - 1;
        if (newStart < 0) {
          newStart = 0;
          newEnd = Math.min(chartData.length - 1, span - 1);
        } else if (newEnd >= chartData.length) {
          newEnd = chartData.length - 1;
          newStart = Math.max(0, newEnd - span + 1);
        } else {
          newStart = Math.max(0, Math.min(newStart, chartData.length - span));
          newEnd = newStart + span - 1;
        }
        return { startIndex: newStart, endIndex: newEnd };
      });
    };
    const onUp = () => setIsPanning(false);
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, [isPanning, chartData.length]);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory]);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch("/api/exchange/status", { cache: "no-store" });
      const json = await res.json();
      setStatus({
        fetching: !!json.fetching,
        totalRecords: Number(json.totalRecords) || 0,
        lastFilledDate: json.lastFilledDate || null,
      });
    } catch {
      setStatus(null);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    const id = setInterval(fetchStatus, 5000);
    return () => clearInterval(id);
  }, [fetchStatus]);

  const currencyLabel = CURRENCY_LABELS[currency];

  const visibleChartData = useMemo(() => {
    if (!brushRange || chartData.length === 0) return chartData;
    return chartData.slice(brushRange.startIndex, brushRange.endIndex + 1);
  }, [chartData, brushRange]);

  const visibleSpan = visibleChartData.length;
  const xAxisTickFormatter = useCallback(
    (value: string, index: number) => {
      if (visibleSpan <= 7) return value;
      const maxTicks = 12;
      const step = Math.max(1, Math.floor(visibleSpan / maxTicks));
      if (index % step === 0 || index === visibleSpan - 1) return value;
      return "";
    },
    [visibleSpan]
  );

  if (loading) {
    return (
      <div className="flex h-full min-h-0 flex-col p-6 md:p-8">
        <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-zinc-100">汇率变动趋势</h1>
            <p className="mt-1 text-sm text-zinc-500">数据自 2025-04-02 起，来源于三方api</p>
          </div>
        </div>
        <div className="flex flex-1 items-center justify-center rounded-xl bg-zinc-900/30 text-zinc-500">
          加载中…
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col p-6 md:p-8">
      <div className="shrink-0 mb-6 pr-8 md:pr-10">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-zinc-100">汇率变动趋势</h1>
            <p className="mt-1 text-sm text-zinc-500">数据自 2025-04-02 起，来源于三方api</p>
          </div>
          <div className="flex shrink-0 overflow-hidden rounded-lg border border-zinc-600">
            {(["usd", "eur", "jpy"] as const).map((c, i) => (
              <button
                key={c}
                type="button"
                onClick={() => setCurrency(c)}
                className={`px-4 py-2 text-sm font-medium transition-all ${
                  i === 0 ? "rounded-l-md" : i === 2 ? "rounded-r-md" : ""
                } ${
                  currency === c
                    ? "bg-[#2563eb]/35 text-white"
                    : "bg-zinc-800/80 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200"
                }`}
              >
                {CURRENCY_LABELS[c]}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="flex-1 min-h-0">
        {chartData.length < 2 ? (
          <div className="flex h-[50vh] min-h-[300px] flex-col items-center justify-center gap-4 rounded-xl bg-zinc-900/30 text-zinc-500">
            <p>暂无汇率数据，请稍后或检查后端定时任务。</p>
            <button
              type="button"
              onClick={() => fetchHistory()}
              className="rounded-lg bg-zinc-700 px-4 py-2 text-sm text-zinc-200 hover:bg-zinc-600"
            >
              刷新
            </button>
          </div>
        ) : (
          <div
            ref={chartContainerRef}
            className="flex h-full min-h-[400px] w-full flex-col rounded-xl bg-zinc-900/30 pl-0 pr-4 pt-4 pb-4 md:pr-6 md:pt-6 md:pb-6 min-h-0"
            style={{ minWidth: 300 }}
          >
            <div
              className="exchange-chart-panable flex min-h-0 flex-1 flex-col"
              style={{
                cursor:
                  brushRange && chartData.length > 1 && brushRange.endIndex - brushRange.startIndex + 1 < chartData.length
                    ? isPanning
                      ? "grabbing"
                      : "grab"
                    : undefined,
                userSelect: isPanning ? "none" : undefined,
              }}
              data-pan={
                brushRange && chartData.length > 1 && brushRange.endIndex - brushRange.startIndex + 1 < chartData.length
                  ? isPanning
                    ? "grabbing"
                    : "grab"
                  : undefined
              }
              onMouseDown={handlePanStart}
            >
            <div className="min-h-0 flex-1">
              <ResponsiveContainer width="100%" height="100%">
              <ComposedChart
                data={visibleChartData}
                margin={{ top: 16, right: 16, left: 0, bottom: 8 }}
              >
                <defs>
                  <linearGradient id="areaGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={CHART_BLUE} stopOpacity={0.35} />
                    <stop offset="100%" stopColor={CHART_BLUE} stopOpacity={0.08} />
                  </linearGradient>
                </defs>
                <CartesianGrid
                  strokeDasharray="3 3"
                  stroke="rgba(255,255,255,0.14)"
                  vertical={true}
                  horizontal={true}
                />
                <XAxis
                  dataKey="date"
                  tick={{ fill: "#a1a1aa", fontSize: 11 }}
                  tickLine={false}
                  axisLine={{ stroke: "rgba(255,255,255,0.08)" }}
                  interval={0}
                  tickFormatter={xAxisTickFormatter}
                />
                <YAxis
                  width={40}
                  tick={{ fill: "#a1a1aa", fontSize: 11 }}
                  tickLine={false}
                  axisLine={{ stroke: "rgba(255,255,255,0.08)" }}
                  tickFormatter={(v) => (Number.isFinite(v) ? String(v) : "")}
                  domain={["auto", "auto"]}
                  tickCount={6}
                />
                <Tooltip
                  content={({ active, payload, label }) => {
                  if (!active || !payload?.length || label == null) return null;
                  const v = payload[0]?.value;
                  return (
                    <div className="rounded-lg border border-zinc-600/80 bg-zinc-900/95 px-4 py-2.5 shadow-xl backdrop-blur-sm">
                      <p className="mb-1 text-xs text-zinc-400">{label}</p>
                      <p className="text-sm font-semibold tabular-nums text-zinc-100">
                        {currencyLabel}: {formatRate(typeof v === "number" ? v : null)}
                      </p>
                    </div>
                  );
                }}
                />
                <Area
                  type="monotone"
                  dataKey="value"
                  fill="url(#areaGradient)"
                  stroke="transparent"
                  baseValue="dataMin"
                  connectNulls
                  legendType="none"
                />
                <Line
                type="monotone"
                dataKey="value"
                name={currencyLabel}
                stroke={CHART_BLUE}
                strokeWidth={2.5}
                dot={<DotEveryThird />}
                activeDot={{ r: 5, stroke: "rgba(255,255,255,0.5)", strokeWidth: 1.5 }}
                connectNulls
              />
              </ComposedChart>
              </ResponsiveContainer>
            </div>
            </div>
            <div ref={brushContainerRef} className="mt-2 h-8 w-full shrink-0">
            <ResponsiveContainer width="100%" height={32}>
              <ComposedChart data={chartData} margin={{ top: 0, right: 16, left: 40, bottom: 0 }}>
                <XAxis dataKey="date" hide />
                <YAxis width={0} hide domain={["auto", "auto"]} />
                <Line type="monotone" dataKey="value" stroke="rgba(255,255,255,0.2)" dot={false} legendType="none" />
                <Brush
                  dataKey="date"
                  height={32}
                  stroke="rgba(255,255,255,0.12)"
                  fill="rgba(39,39,42,0.6)"
                  traveller={(props: { x?: number; y?: number; width?: number; height?: number }) => (
                    <rect
                      {...props}
                      fill="rgba(37,99,235,0.5)"
                      stroke="rgba(255,255,255,0.25)"
                      strokeWidth={1}
                    />
                  )}
                  startIndex={Math.min(
                    chartData.length - 1,
                    Math.max(0, brushRange?.startIndex ?? Math.max(0, chartData.length - DEFAULT_DAYS))
                  )}
                  endIndex={Math.min(
                    chartData.length - 1,
                    Math.max(0, brushRange?.endIndex ?? chartData.length - 1)
                  )}
                  onChange={(range) => {
                    if (range && typeof range.startIndex === "number" && typeof range.endIndex === "number") {
                      setBrushRange({ startIndex: range.startIndex, endIndex: range.endIndex });
                    }
                  }}
                />
              </ComposedChart>
            </ResponsiveContainer>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
