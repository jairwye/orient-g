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
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { AnalystInsightStrip } from "../components/AnalystInsightStrip";
import { CashQualityMatrix } from "../components/CashQualityMatrix";
import { ChapterPanel } from "../components/ChapterPanel";
import { ChartPanel } from "../components/ChartPanel";
import { CompetitorChartTooltip, competitorBarTooltipProps } from "../components/CompetitorChartTooltip";
import { DataTable } from "../components/DataTable";
import { NarrativesFromSection } from "../components/NarrativeBlock";
import { BUSINESS_CHART_COLORS } from "../../lib/business_chart_colors";
import { CHART_CARTESIAN_GRID, CHART_X_AXIS, CHART_Y_AXIS } from "../lib/competitor_chart_colors";
import { COMPANY_COLS, colToLabel } from "../lib/companies";
import {
  deriveCfItemsInsights,
  deriveCfQualityInsights,
  parseCashQualityPoints,
} from "../lib/finance_analysis";
import { CL, FK, FK_CF_ITEM } from "../lib/field_keys";
import { formatDecimal2, formatPctPoints, formatYiWan, parseNum } from "../lib/format";
import { subTitleForSnap } from "../lib/navigation";
import { getTable } from "../lib/selectors";
import { type SectionProps } from "../lib/section_ui";

function cfRow(table: ReturnType<typeof getTable>, part: string) {
  return table?.rows.find((r) => String(r[FK_CF_ITEM] ?? "").replace(/\*\*/g, "").includes(part));
}

function ratioBarColor(ratioPct: number, profit: number | null): string {
  if (profit != null && profit < 0) return "#71717a";
  if (ratioPct >= 100) return BUSINESS_CHART_COLORS.actual;
  if (ratioPct >= 50) return BUSINESS_CHART_COLORS.current;
  return "#ef4444";
}

export function Sec08Cashflow({ snapshot }: SectionProps) {
  const sec08 = snapshot.sections.find((s) => s.id === "sec-08");
  const cfItems = getTable(snapshot, "sec-08-1");
  const cfQuality = getTable(snapshot, "sec-08-2");

  const itemsInsights = useMemo(() => deriveCfItemsInsights(snapshot), [snapshot]);
  const qualityInsights = useMemo(() => deriveCfQualityInsights(snapshot), [snapshot]);
  const qualityPoints = useMemo(() => parseCashQualityPoints(snapshot), [snapshot]);

  const threeBuckets = useMemo(() => {
    const ocf = cfRow(cfItems, "\u7ecf\u8425CF\u51c0\u989d");
    const icf = cfRow(cfItems, "\u6295\u8d44CF\u51c0\u989d");
    const fcf = cfRow(cfItems, "\u7b79\u8d44CF\u51c0\u989d");
    if (!ocf && !icf && !fcf) return [];
    return COMPANY_COLS.map((col) => ({
      name: colToLabel(col),
      operating: parseNum(ocf?.[col] ?? null) ?? 0,
      investing: parseNum(icf?.[col] ?? null) ?? 0,
      financing: parseNum(fcf?.[col] ?? null) ?? 0,
    })).sort((a, b) => b.operating - a.operating);
  }, [cfItems]);

  const cashDeltaData = useMemo(() => {
    const row = cfItems?.rows.find((r) => String(r[FK_CF_ITEM] ?? "").includes("\u73b0\u91d1\u51c0\u589e\u52a0"));
    if (!row) return [];
    return COMPANY_COLS.map((col) => {
      const v = parseNum(row[col]);
      if (v == null) return null;
      return {
        name: colToLabel(col),
        value: v,
        fill: v >= 0 ? BUSINESS_CHART_COLORS.actual : "#ef4444",
      };
    })
      .filter(Boolean)
      .sort((a, b) => b!.value - a!.value);
  }, [cfItems]);

  const profitRow = cfQuality?.rows.find((r) => String(r[FK.metric] ?? "").includes(CL.netProfit));
  const ocfRow = cfQuality?.rows.find((r) => String(r[FK.metric] ?? "").includes(CL.ocf));

  const compareData = useMemo(
    () =>
      COMPANY_COLS.map((col) => {
        const profit = profitRow ? parseNum(profitRow[col]) : null;
        const ocf = ocfRow ? parseNum(ocfRow[col]) : null;
        if (profit == null && ocf == null) return null;
        return {
          name: colToLabel(col),
          profit: profit ?? 0,
          ocf: ocf ?? 0,
          sortKey: ocf ?? profit ?? 0,
        };
      })
        .filter(Boolean)
        .sort((a, b) => b!.sortKey - a!.sortKey),
    [profitRow, ocfRow],
  );

  const ratioData = useMemo(
    () =>
      qualityPoints.map((p) => ({
        name: p.name,
        ratio: Math.min(Math.max(p.ratioPct, -120), 200),
        profit: p.profit,
        fill: ratioBarColor(p.ratioPct, p.profit),
      })),
    [qualityPoints],
  );

  const chartH = Math.max(280, compareData.length * 44 + 72);
  const bucketH = Math.max(260, threeBuckets.length * 38 + 64);

  return (
    <ChapterPanel
      sectionId="sec-08"
      slides={[
        {
          id: "sec-08-a",
          title: subTitleForSnap("sec-08-a"),
          content: (
            <>
              <AnalystInsightStrip insights={itemsInsights} />
              {cfItems ? (
                <DataTable title={CL.cfItems} headers={cfItems.headers} rows={cfItems.rows} delayMs={60} compact />
              ) : null}
              <div className="mt-5 grid gap-5 lg:grid-cols-2 lg:gap-6">
                <ChartPanel title={CL.cfThreeBuckets} delayMs={100} height="h-auto min-h-[260px]">
                  <div style={{ height: bucketH }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={threeBuckets} layout="vertical" margin={{ left: 4, right: 16, top: 4, bottom: 4 }}>
                        <CartesianGrid {...CHART_CARTESIAN_GRID} horizontal={false} />
                        <XAxis type="number" {...CHART_X_AXIS} tick={{ fontSize: 10 }} />
                        <YAxis type="category" dataKey="name" {...CHART_Y_AXIS} width={80} interval={0} tick={{ fontSize: 10 }} />
                        <ReferenceLine x={0} stroke="#52525b" />
                        <Tooltip {...competitorBarTooltipProps({ content: <CompetitorChartTooltip valueFormatter={(v) => formatYiWan(v)} /> })} />
                        <Legend wrapperStyle={{ fontSize: 10 }} />
                        <Bar dataKey="operating" name={CL.ocf} fill={BUSINESS_CHART_COLORS.actual} radius={[0, 3, 3, 0]} />
                        <Bar dataKey="investing" name={CL.cfInvesting} fill="#d97706" radius={[0, 3, 3, 0]} />
                        <Bar dataKey="financing" name={CL.cfFinancing} fill={BUSINESS_CHART_COLORS.current} radius={[0, 3, 3, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </ChartPanel>
                <ChartPanel title={CL.cashNetIncreaseYoY} delayMs={140} height="h-auto min-h-[240px]">
                  <div style={{ height: Math.max(220, cashDeltaData.length * 34 + 52) }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={cashDeltaData} layout="vertical" margin={{ left: 4, right: 16, top: 4, bottom: 4 }}>
                        <CartesianGrid {...CHART_CARTESIAN_GRID} horizontal={false} />
                        <XAxis type="number" {...CHART_X_AXIS} tick={{ fontSize: 10 }} />
                        <YAxis type="category" dataKey="name" {...CHART_Y_AXIS} width={80} interval={0} tick={{ fontSize: 10 }} />
                        <ReferenceLine x={0} stroke="#52525b" />
                        <Tooltip {...competitorBarTooltipProps({ content: <CompetitorChartTooltip valueFormatter={(v) => formatYiWan(v)} /> })} />
                        <Bar dataKey="value" name={CL.cashNetIncrease} radius={[0, 3, 3, 0]}>
                          {cashDeltaData.map((d, i) => (
                            <Cell key={i} fill={d!.fill} />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </ChartPanel>
              </div>
            </>
          ),
        },
        {
          id: "sec-08-b",
          title: subTitleForSnap("sec-08-b"),
          content: (
            <>
              <AnalystInsightStrip insights={qualityInsights} delayMs={40} />
              {cfQuality ? (
                <DataTable title={CL.profitVsOcf} headers={cfQuality.headers} rows={cfQuality.rows} delayMs={60} compact />
              ) : null}
              <div className="mt-5">
                <ChartPanel title={CL.profitVsOcf} delayMs={100} height="h-auto min-h-[280px]">
                  <div style={{ height: chartH }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={compareData} layout="vertical" margin={{ left: 4, right: 16, top: 4, bottom: 4 }} barGap={4}>
                        <CartesianGrid {...CHART_CARTESIAN_GRID} horizontal={false} />
                        <XAxis type="number" {...CHART_X_AXIS} tickFormatter={(v) => formatDecimal2(v)} tick={{ fontSize: 10 }} />
                        <YAxis type="category" dataKey="name" {...CHART_Y_AXIS} width={80} interval={0} tick={{ fontSize: 10 }} />
                        <ReferenceLine x={0} stroke="#52525b" />
                        <Tooltip {...competitorBarTooltipProps({ content: <CompetitorChartTooltip valueFormatter={(v) => formatYiWan(v)} /> })} />
                        <Legend wrapperStyle={{ fontSize: 11 }} />
                        <Bar dataKey="profit" name={CL.netProfit} fill={BUSINESS_CHART_COLORS.current} radius={[0, 3, 3, 0]} />
                        <Bar dataKey="ocf" name={CL.ocf} fill={BUSINESS_CHART_COLORS.actual} radius={[0, 3, 3, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </ChartPanel>
              </div>
              <div className="mt-5">
                <CashQualityMatrix points={qualityPoints} snapshot={snapshot} delayMs={140} />
              </div>
              {ratioData.length > 0 && (
                <ChartPanel title={CL.ocfRatio} delayMs={180} height="h-auto min-h-[260px]">
                  <div style={{ height: chartH }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={ratioData} layout="vertical" margin={{ left: 4, right: 16, top: 4, bottom: 4 }}>
                        <CartesianGrid {...CHART_CARTESIAN_GRID} horizontal={false} />
                        <XAxis type="number" domain={[-20, 180]} {...CHART_X_AXIS} unit="%" tick={{ fontSize: 10 }} />
                        <YAxis type="category" dataKey="name" {...CHART_Y_AXIS} width={80} interval={0} tick={{ fontSize: 10 }} />
                        <ReferenceLine x={100} stroke="#22c55e" strokeDasharray="4 4" />
                        <Tooltip {...competitorBarTooltipProps({ content: <CompetitorChartTooltip valueFormatter={(v) => formatPctPoints(v)} /> })} />
                        <Bar dataKey="ratio" name={CL.ocfRatio} radius={[0, 3, 3, 0]}>
                          {ratioData.map((d, i) => (
                            <Cell key={i} fill={d.fill} />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </ChartPanel>
              )}
              <div className="mt-5 sm:mt-6">
                <NarrativesFromSection blocks={sec08?.blocks ?? []} anchor="sec-08-2" plain stripAnalysisPrefix />
              </div>
            </>
          ),
        },
      ]}
    />
  );
}
