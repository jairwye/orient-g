"use client";

import { useMemo } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";
import { AnalystInsightStrip } from "../components/AnalystInsightStrip";
import { ChapterPanel } from "../components/ChapterPanel";
import { ChartPanel } from "../components/ChartPanel";
import {
  CompetitorChartTooltip,
  competitorBarTooltipProps,
  competitorScatterTooltipProps,
} from "../components/CompetitorChartTooltip";
import { DataTable } from "../components/DataTable";
import { DivergingBarPanel } from "../components/DivergingBarPanel";
import { NarrativesFromSection } from "../components/NarrativeBlock";
import { BUSINESS_CHART_COLORS } from "../../lib/business_chart_colors";
import {
  CHART_CARTESIAN_GRID,
  CHART_X_AXIS,
  CHART_Y_AXIS,
  colorForCompany,
} from "../lib/competitor_chart_colors";
import { COMPANY_COLS, colToLabel } from "../lib/companies";
import {
  computeOperatingMargins,
  deriveFeeAmountInsights,
  deriveFeeRateChangeInsights,
  deriveFeeRateInsights,
  deriveProfitCoreInsights,
  deriveProfitDriverInsights,
  peerMedian,
} from "../lib/finance_analysis";
import { CL, FK, FK_AMOUNT_CHANGE } from "../lib/field_keys";
import { formatPctPoints, formatYiWan, parseNum, toPercentPoints } from "../lib/format";
import { subTitleForSnap } from "../lib/navigation";
import { getTable } from "../lib/selectors";
import { type SectionProps } from "../lib/section_ui";

const FEE_STACK = [
  { key: FK.salesFeeRate, color: BUSINESS_CHART_COLORS.current },
  { key: FK.adminFeeRate, color: "#d97706" },
  { key: FK.rndFeeRate, color: "#7c3aed" },
] as const;

const FEE_CHANGE_METRICS = [FK.grossMarginRate, FK.salesFeeRate, FK.adminFeeRate, FK.rndFeeRate] as const;

const FEE_AMOUNT_ROWS = ["营业成本", "毛利", "销售费用", "管理费用", "研发费用"] as const;

function pctPoints(v: number | null): number | null {
  if (v == null) return null;
  return toPercentPoints(v);
}

function deltaFill(metric: string, delta: number): string {
  const isFee = metric !== FK.grossMarginRate;
  if (isFee) return delta <= 0 ? BUSINESS_CHART_COLORS.actual : "#ef4444";
  return delta >= 0 ? BUSINESS_CHART_COLORS.actual : "#ef4444";
}

function subjectRow(table: ReturnType<typeof getTable>, prefix: string) {
  return table?.rows.find((r) => String(r[FK.subject] ?? "").startsWith(prefix));
}

function buildAmountChangeBars(table: ReturnType<typeof getTable>, subject: string) {
  const row = table?.rows.find((r) => String(r[FK_AMOUNT_CHANGE] ?? "") === subject);
  if (!row) return [];
  return COMPANY_COLS.map((col) => {
    const delta = parseNum(row[col]);
    if (delta == null) return null;
    const isCostLike = subject === "销售费用" || subject === "管理费用" || subject === "研发费用" || subject === "营业成本";
    const good = isCostLike ? delta <= 0 : delta >= 0;
    return {
      name: colToLabel(col),
      delta,
      fill: good ? BUSINESS_CHART_COLORS.actual : "#ef4444",
    };
  })
    .filter(Boolean)
    .sort((a, b) => b!.delta - a!.delta) as Array<{ name: string; delta: number; fill: string }>;
}

export function Sec07Profit({ snapshot }: SectionProps) {
  const sec07 = snapshot.sections.find((s) => s.id === "sec-07");
  const core = getTable(snapshot, "sec-07-1");
  const drivers = getTable(snapshot, "sec-07-2");
  const fees = getTable(snapshot, "sec-07-3");
  const feePctChg = getTable(snapshot, "sec-07-4");
  const feeAmtChg = getTable(snapshot, "sec-07-5");

  const coreInsights = useMemo(() => deriveProfitCoreInsights(snapshot), [snapshot]);
  const driverInsights = useMemo(() => deriveProfitDriverInsights(snapshot), [snapshot]);
  const feeInsights = useMemo(() => deriveFeeRateInsights(snapshot), [snapshot]);
  const pctInsights = useMemo(() => deriveFeeRateChangeInsights(snapshot), [snapshot]);
  const amtInsights = useMemo(() => deriveFeeAmountInsights(snapshot), [snapshot]);
  const opMargins = useMemo(() => computeOperatingMargins(snapshot), [snapshot]);

  const revProfitData = useMemo(() => {
    const rev = subjectRow(core, "\u8425\u4e1a\u6536\u5165");
    const profit = subjectRow(core, "\u51c0\u5229\u6da6");
    if (!rev || !profit) return [];
    return COMPANY_COLS.map((col) => {
      const r = parseNum(rev[col]);
      const p = parseNum(profit[col]);
      if (r == null && p == null) return null;
      return { name: colToLabel(col), revenue: r ?? 0, profit: p ?? 0 };
    })
      .filter(Boolean)
      .sort((a, b) => b!.revenue - a!.revenue);
  }, [core]);

  const salesCostData = useMemo(() => {
    const sales = subjectRow(core, "\u9500\u552e\u8d39\u7528");
    const cost = subjectRow(core, "\u8425\u4e1a\u6210\u672c");
    if (!sales || !cost) return [];
    return COMPANY_COLS.map((col) => {
      const s = parseNum(sales[col]);
      const c = parseNum(cost[col]);
      if (s == null && c == null) return null;
      return { name: colToLabel(col), sales: s ?? 0, cost: c ?? 0 };
    })
      .filter(Boolean)
      .sort((a, b) => b!.sales - a!.sales);
  }, [core]);

  const feeStackData = useMemo(
    () =>
      COMPANY_COLS.map((col) => {
        const point: Record<string, string | number> = { name: colToLabel(col) };
        let hasAny = false;
        for (const { key } of FEE_STACK) {
          const row = fees?.rows.find((r) => String(r[FK.metric] ?? "") === key);
          const v = row ? pctPoints(parseNum(row[col])) : null;
          if (v != null) {
            point[key] = v;
            hasAny = true;
          }
        }
        return hasAny ? point : null;
      }).filter(Boolean),
    [fees?.rows],
  );

  const grossMarginData = useMemo(
    () =>
      COMPANY_COLS.map((col) => {
        const row = fees?.rows.find((r) => String(r[FK.metric] ?? "") === FK.grossMarginRate);
        const v = row ? pctPoints(parseNum(row[col])) : null;
        if (v == null) return null;
        return { name: colToLabel(col), value: v, fill: colorForCompany(col, snapshot) };
      })
        .filter(Boolean)
        .sort((a, b) => b!.value - a!.value),
    [fees?.rows, snapshot],
  );

  const opMarginData = useMemo(
    () =>
      opMargins
        .map((d) => ({
          name: d.name,
          opMargin: d.opMargin,
          fill: colorForCompany(d.colKey, snapshot),
        }))
        .sort((a, b) => b.opMargin - a.opMargin),
    [opMargins, snapshot],
  );

  const modelScatter = useMemo(
    () =>
      opMargins.map((d) => ({
        ...d,
        fill: colorForCompany(d.colKey, snapshot),
        z: Math.max(60, Math.min(400, Math.abs(d.opMargin) * 4 + 80)),
      })),
    [opMargins, snapshot],
  );

  const pctChangeCharts = useMemo(() => {
    if (!feePctChg?.rows.length) return [];
    return FEE_CHANGE_METRICS.map((metric) => {
      const row = feePctChg.rows.find((r) => String(r[FK.changePct] ?? "") === metric);
      if (!row) return null;
      const data = COMPANY_COLS.map((col) => {
        const raw = parseNum(row[col]);
        if (raw == null) return null;
        return { name: colToLabel(col), delta: raw, fill: deltaFill(metric, raw) };
      })
        .filter(Boolean)
        .sort((a, b) => b!.delta - a!.delta);
      if (!data.length) return null;
      return { metric, data };
    }).filter(Boolean) as Array<{ metric: string; data: Array<{ name: string; delta: number; fill: string }> }>;
  }, [feePctChg?.rows]);

  const amtChangeCharts = useMemo(
    () =>
      FEE_AMOUNT_ROWS.map((subject) => ({
        subject,
        data: buildAmountChangeBars(feeAmtChg, subject),
      })).filter((x) => x.data.length > 0),
    [feeAmtChg],
  );

  const medGross = peerMedian(modelScatter.map((d) => d.gross));
  const medSales = peerMedian(modelScatter.map((d) => d.sales));
  const chartH = Math.max(260, (feeStackData.length || 8) * 38 + 64);

  return (
    <ChapterPanel
      sectionId="sec-07"
      slides={[
        {
          id: "sec-07-a",
          title: subTitleForSnap("sec-07-a"),
          content: (
            <>
              <AnalystInsightStrip insights={coreInsights} />
              {core ? (
                <DataTable title={CL.profitCoreItems} headers={core.headers} rows={core.rows} delayMs={60} compact />
              ) : null}
              <div className="mt-5 grid gap-5 lg:grid-cols-2 lg:gap-6">
                <ChartPanel title={CL.revenueVsProfit} delayMs={100} height="h-auto min-h-[260px]">
                  <div style={{ height: chartH }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={revProfitData} layout="vertical" margin={{ left: 4, right: 16, top: 4, bottom: 4 }}>
                        <CartesianGrid {...CHART_CARTESIAN_GRID} horizontal={false} />
                        <XAxis type="number" {...CHART_X_AXIS} tick={{ fontSize: 10 }} />
                        <YAxis type="category" dataKey="name" {...CHART_Y_AXIS} width={80} interval={0} tick={{ fontSize: 10 }} />
                        <ReferenceLine x={0} stroke="#52525b" />
                        <Tooltip {...competitorBarTooltipProps({ content: <CompetitorChartTooltip valueFormatter={(v) => formatYiWan(v)} /> })} />
                        <Legend wrapperStyle={{ fontSize: 10 }} />
                        <Bar dataKey="revenue" name={CL.revenue} fill={BUSINESS_CHART_COLORS.current} radius={[0, 3, 3, 0]} />
                        <Bar dataKey="profit" name={CL.profit} fill={BUSINESS_CHART_COLORS.actual} radius={[0, 3, 3, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </ChartPanel>
                <ChartPanel title={CL.salesVsCost} delayMs={140} height="h-auto min-h-[260px]">
                  <div style={{ height: chartH }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={salesCostData} layout="vertical" margin={{ left: 4, right: 16, top: 4, bottom: 4 }}>
                        <CartesianGrid {...CHART_CARTESIAN_GRID} horizontal={false} />
                        <XAxis type="number" {...CHART_X_AXIS} tick={{ fontSize: 10 }} />
                        <YAxis type="category" dataKey="name" {...CHART_Y_AXIS} width={80} interval={0} tick={{ fontSize: 10 }} />
                        <Tooltip {...competitorBarTooltipProps({ content: <CompetitorChartTooltip valueFormatter={(v) => formatYiWan(v)} /> })} />
                        <Legend wrapperStyle={{ fontSize: 10 }} />
                        <Bar dataKey="sales" name={CL.salesExpenseWan} fill="#2563eb" radius={[0, 3, 3, 0]} />
                        <Bar dataKey="cost" name={CL.operatingCost} fill="#d97706" radius={[0, 3, 3, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                  <p className="mt-2 text-xs text-zinc-500">销售费用 &gt; 营业成本时即为买量驱动型（三七互娱蓝本要点）。</p>
                </ChartPanel>
              </div>
              <div className="mt-5 sm:mt-6">
                <NarrativesFromSection blocks={sec07?.blocks ?? []} anchor="sec-07-1" plain stripAnalysisPrefix />
              </div>
            </>
          ),
        },
        {
          id: "sec-07-b",
          title: subTitleForSnap("sec-07-b"),
          content: (
            <>
              <AnalystInsightStrip insights={driverInsights} delayMs={40} />
              {drivers ? (
                <DataTable title={CL.profitDrivers} headers={drivers.headers} rows={drivers.rows} delayMs={60} compact />
              ) : null}
            </>
          ),
        },
        {
          id: "sec-07-c",
          title: subTitleForSnap("sec-07-c"),
          content: (
            <>
              <AnalystInsightStrip insights={feeInsights} delayMs={40} />
              {fees ? (
                <DataTable title={CL.feeRates} headers={fees.headers} rows={fees.rows} delayMs={60} compact />
              ) : null}
              <div className="mt-5 grid gap-5 lg:grid-cols-2 lg:gap-6">
                <ChartPanel title={CL.operatingMargin} delayMs={100} height="h-auto min-h-[260px]">
                  <div style={{ height: chartH }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={opMarginData} layout="vertical" margin={{ left: 4, right: 16, top: 4, bottom: 4 }}>
                        <CartesianGrid {...CHART_CARTESIAN_GRID} horizontal={false} />
                        <XAxis type="number" {...CHART_X_AXIS} unit="%" tick={{ fontSize: 10 }} />
                        <YAxis type="category" dataKey="name" {...CHART_Y_AXIS} width={80} interval={0} tick={{ fontSize: 10 }} />
                        <ReferenceLine x={0} stroke="#52525b" />
                        <Tooltip {...competitorBarTooltipProps({ content: <CompetitorChartTooltip valueFormatter={(v) => formatPctPoints(v)} /> })} />
                        <Bar dataKey="opMargin" name={CL.operatingMargin} radius={[0, 3, 3, 0]}>
                          {opMarginData.map((d, i) => (
                            <Cell key={i} fill={d.opMargin >= 0 ? d.fill : "#ef4444"} />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </ChartPanel>
                <ChartPanel title={CL.profitModelQuadrant} delayMs={140} height="h-auto min-h-[280px]">
                  <div style={{ height: 300 }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <ScatterChart margin={{ top: 8, right: 16, bottom: 24, left: 8 }}>
                        <CartesianGrid {...CHART_CARTESIAN_GRID} />
                        <XAxis type="number" dataKey="gross" unit="%" {...CHART_X_AXIS} tick={{ fontSize: 10 }} />
                        <YAxis type="number" dataKey="sales" unit="%" {...CHART_Y_AXIS} width={36} tick={{ fontSize: 10 }} />
                        <ZAxis type="number" dataKey="z" range={[60, 360]} />
                        {medGross != null && <ReferenceLine x={medGross} stroke="#52525b" strokeDasharray="4 4" />}
                        {medSales != null && <ReferenceLine y={medSales} stroke="#52525b" strokeDasharray="4 4" />}
                        <Tooltip {...competitorScatterTooltipProps({ content: <CompetitorChartTooltip /> })} />
                        <Scatter data={modelScatter}>
                          {modelScatter.map((d, i) => (
                            <Cell key={i} fill={d.fill} />
                          ))}
                        </Scatter>
                      </ScatterChart>
                    </ResponsiveContainer>
                  </div>
                </ChartPanel>
                <ChartPanel title={CL.grossMarginRank} delayMs={180} height="h-auto min-h-[240px]">
                  <div style={{ height: chartH }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={grossMarginData} layout="vertical" margin={{ left: 4, right: 16, top: 4, bottom: 4 }}>
                        <CartesianGrid {...CHART_CARTESIAN_GRID} horizontal={false} />
                        <XAxis type="number" domain={[0, 100]} {...CHART_X_AXIS} unit="%" tick={{ fontSize: 10 }} />
                        <YAxis type="category" dataKey="name" {...CHART_Y_AXIS} width={80} interval={0} tick={{ fontSize: 10 }} />
                        <Tooltip {...competitorBarTooltipProps({ content: <CompetitorChartTooltip valueFormatter={(v) => formatPctPoints(v)} /> })} />
                        <Bar dataKey="value" name={FK.grossMarginRate} radius={[0, 3, 3, 0]}>
                          {grossMarginData.map((d, i) => (
                            <Cell key={i} fill={d!.fill} />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </ChartPanel>
                <ChartPanel title={CL.feeStackHoriz} delayMs={220} height="h-auto min-h-[240px]">
                  <div style={{ height: chartH }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={feeStackData} layout="vertical" margin={{ left: 4, right: 16, top: 4, bottom: 4 }}>
                        <CartesianGrid {...CHART_CARTESIAN_GRID} horizontal={false} />
                        <XAxis type="number" domain={[0, "auto"]} {...CHART_X_AXIS} unit="%" tick={{ fontSize: 10 }} />
                        <YAxis type="category" dataKey="name" {...CHART_Y_AXIS} width={80} interval={0} tick={{ fontSize: 10 }} />
                        <Tooltip {...competitorBarTooltipProps({ content: <CompetitorChartTooltip valueFormatter={(v) => formatPctPoints(v)} /> })} />
                        <Legend wrapperStyle={{ fontSize: 10 }} />
                        {FEE_STACK.map(({ key, color }) => (
                          <Bar key={key} dataKey={key} name={key} stackId="fee" fill={color} fillOpacity={0.9} />
                        ))}
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </ChartPanel>
              </div>
            </>
          ),
        },
        {
          id: "sec-07-d",
          title: subTitleForSnap("sec-07-d"),
          content: (
            <>
              <AnalystInsightStrip insights={pctInsights} delayMs={40} />
              {feePctChg ? (
                <DataTable title={CL.feeRateYoYTable} headers={feePctChg.headers} rows={feePctChg.rows} delayMs={60} compact />
              ) : null}
              <div className="mt-5 grid gap-4 sm:grid-cols-2">
                {pctChangeCharts.map(({ metric, data }, idx) => (
                  <DivergingBarPanel
                    key={metric}
                    title={`${CL.feeRateYoY} · ${metric}`}
                    data={data}
                    delayMs={80 + idx * 40}
                    unit="pct"
                  />
                ))}
              </div>
            </>
          ),
        },
        {
          id: "sec-07-e",
          title: subTitleForSnap("sec-07-e"),
          content: (
            <>
              <AnalystInsightStrip insights={amtInsights} delayMs={40} />
              {feeAmtChg ? (
                <DataTable title={CL.feeAmountYoY} headers={feeAmtChg.headers} rows={feeAmtChg.rows} delayMs={60} compact />
              ) : null}
              <div className="mt-5 grid gap-4 sm:grid-cols-2">
                {amtChangeCharts.map(({ subject, data }, idx) => (
                  <DivergingBarPanel
                    key={subject}
                    title={`${CL.feeAmountYoY} · ${subject}`}
                    data={data}
                    delayMs={80 + idx * 40}
                    unit="wan"
                  />
                ))}
              </div>
              <div className="mt-5 sm:mt-6">
                <NarrativesFromSection blocks={sec07?.blocks ?? []} anchor="sec-07-5" plain stripAnalysisPrefix />
              </div>
            </>
          ),
        },
      ]}
    />
  );
}
