"use client";

import { useMemo, type ReactNode } from "react";
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
import { AnalystInsightStrip } from "../components/AnalystInsightStrip";
import { ChapterPanel } from "../components/ChapterPanel";
import { ChartPanel } from "../components/ChartPanel";
import { CompetitorChartTooltip, competitorBarTooltipProps } from "../components/CompetitorChartTooltip";
import { DataTable } from "../components/DataTable";
import { NarrativesFromSection } from "../components/NarrativeBlock";
import { BUSINESS_CHART_COLORS } from "../../lib/business_chart_colors";
import { CHART_CARTESIAN_GRID, CHART_X_AXIS, CHART_Y_AXIS, colorForCompany } from "../lib/competitor_chart_colors";
import { COMPANY_COLS, colToLabel } from "../lib/companies";
import {
  acquisitionModel,
  deriveArAgingInsights,
  deriveCurrencyInsights,
  deriveGovInsights,
  deriveInvestmentInsights,
  derivePipelineInsights,
  deriveProductsInsights,
  deriveRentInsights,
  deriveRoiInsights,
} from "../lib/finance_analysis";
import { CL, FK, FK_METRIC } from "../lib/field_keys";
import { formatDecimal2, formatPctPoints, parseNum, toPercentPoints } from "../lib/format";
import { subTitleForSnap } from "../lib/navigation";
import { getTable } from "../lib/selectors";
import { type SectionProps } from "../lib/section_ui";

function metricBars(
  table: ReturnType<typeof getTable>,
  metric: string,
  snapshot: SectionProps["snapshot"],
  opts?: { asPct?: boolean },
) {
  const row = table?.rows.find((r) => String(r[FK.metric] ?? "") === metric);
  if (!row) return [];
  return COMPANY_COLS.map((col) => {
    const raw = parseNum(row[col]);
    if (raw == null) return null;
    const value = opts?.asPct ? toPercentPoints(raw) : raw;
    return { name: colToLabel(col), value, fill: colorForCompany(col, snapshot) };
  })
    .filter(Boolean)
    .sort((a, b) => b!.value - a!.value) as Array<{ name: string; value: number; fill: string }>;
}

function AnchorSlide({
  insights,
  table,
  tableTitle,
  narrativeAnchor,
  blocks,
  delayMs = 40,
  chart,
  dense,
}: {
  insights: ReturnType<typeof deriveRoiInsights>;
  table?: ReturnType<typeof getTable>;
  tableTitle?: string;
  narrativeAnchor?: string;
  blocks: SectionProps["snapshot"]["sections"][0]["blocks"];
  delayMs?: number;
  chart?: ReactNode;
  dense?: boolean;
}) {
  return (
    <div className={dense ? "space-y-4 sm:space-y-5" : "space-y-5 sm:space-y-6"}>
      <AnalystInsightStrip insights={insights} delayMs={delayMs} />
      {table && table.rows.length > 0 ? (
        <DataTable title={tableTitle} headers={table.headers} rows={table.rows} delayMs={delayMs + 20} compact />
      ) : null}
      {chart}
      {narrativeAnchor ? (
        <NarrativesFromSection blocks={blocks} anchor={narrativeAnchor} plain stripAnalysisPrefix />
      ) : null}
    </div>
  );
}

export function Sec09Others({ snapshot }: SectionProps) {
  const sec09 = snapshot.sections.find((s) => s.id === "sec-09");
  const blocks = sec09?.blocks ?? [];

  const rent = getTable(snapshot, "sec-09-1");
  const roi = getTable(snapshot, "sec-09-2");
  const gov = getTable(snapshot, "sec-09-3");
  const rndProjects = getTable(snapshot, "sec-09-4");
  const dividend = getTable(snapshot, "sec-09-5");
  const currency = getTable(snapshot, "sec-09-6");
  const investment = getTable(snapshot, "sec-09-7");
  const arAging = getTable(snapshot, "sec-09-8");
  const products = getTable(snapshot, "sec-09-9");

  const rentInsights = useMemo(() => deriveRentInsights(snapshot), [snapshot]);
  const roiInsights = useMemo(() => deriveRoiInsights(snapshot), [snapshot]);
  const govInsights = useMemo(() => deriveGovInsights(snapshot), [snapshot]);
  const pipeInsights = useMemo(() => derivePipelineInsights(snapshot), [snapshot]);
  const fxInsights = useMemo(() => deriveCurrencyInsights(snapshot), [snapshot]);
  const invInsights = useMemo(() => deriveInvestmentInsights(snapshot), [snapshot]);
  const arInsights = useMemo(() => deriveArAgingInsights(snapshot), [snapshot]);
  const prodInsights = useMemo(() => deriveProductsInsights(snapshot), [snapshot]);

  const roiData = useMemo(() => metricBars(roi, FK_METRIC.compositeRoi, snapshot), [roi, snapshot]);
  const rentData = useMemo(() => metricBars(rent, FK_METRIC.rentPerCap, snapshot), [rent, snapshot]);

  const adShareData = useMemo(() => {
    const row = roi?.rows.find((r) => String(r[FK.metric] ?? "") === FK_METRIC.adSalesRatio);
    if (!row) return [];
    return COMPANY_COLS.map((col) => {
      const raw = parseNum(row[col]);
      if (raw == null) return null;
      const pct = toPercentPoints(raw);
      return {
        name: colToLabel(col),
        value: pct,
        modelLabel: acquisitionModel(pct).label,
        fill: colorForCompany(col, snapshot),
      };
    }).filter(Boolean).sort((a, b) => b!.value - a!.value);
  }, [roi, snapshot]);

  const fxMixData = useMemo(() => {
    const rmbRow = currency?.rows.find((r) => String(r[FK.metric] ?? "").includes("\u4eba\u6c11\u5e01\u5360\u6bd4"));
    const fxRow = currency?.rows.find((r) => String(r[FK.metric] ?? "").includes("\u5916\u5e01\u5360\u6bd4"));
    if (!rmbRow && !fxRow) return [];
    return COMPANY_COLS.map((col) => {
      const rmb = rmbRow ? toPercentPoints(parseNum(rmbRow[col]) ?? 0) : 0;
      const fx = fxRow ? toPercentPoints(parseNum(fxRow[col]) ?? 0) : 0;
      if (rmb === 0 && fx === 0) return null;
      return { name: colToLabel(col), rmb, fx };
    }).filter(Boolean);
  }, [currency]);

  const arOver1y = useMemo(() => {
    if (!arAging?.rows.length) return [];
    return arAging.rows
      .map((row) => {
        const co = String(row[FK.company] ?? "");
        const pct = parseNum(row["1\u5e74\u4ee5\u4e0a\u5360\u6bd4"]);
        if (pct == null) return null;
        return { name: co === "YYCQ" ? FK.yycqLabel : co, value: toPercentPoints(pct) };
      })
      .filter(Boolean)
      .sort((a, b) => b!.value - a!.value);
  }, [arAging?.rows]);

  const chartH = Math.max(240, roiData.length * 36 + 56);

  const roiCharts = (
    <div className="mt-5 grid gap-5 lg:grid-cols-2 lg:gap-6">
      <ChartPanel title={CL.compositeRoi} delayMs={100} height="h-auto min-h-[240px]">
        <div style={{ height: chartH }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={roiData} layout="vertical" margin={{ left: 4, right: 16, top: 4, bottom: 4 }}>
              <CartesianGrid {...CHART_CARTESIAN_GRID} horizontal={false} />
              <XAxis type="number" {...CHART_X_AXIS} unit="x" tick={{ fontSize: 10 }} />
              <YAxis type="category" dataKey="name" {...CHART_Y_AXIS} width={80} interval={0} tick={{ fontSize: 10 }} />
              <Tooltip {...competitorBarTooltipProps({ content: <CompetitorChartTooltip valueFormatter={(v) => `${formatDecimal2(v)}x`} /> })} />
              <Bar dataKey="value" name={CL.compositeRoi} radius={[0, 3, 3, 0]}>
                {roiData.map((d, i) => (
                  <Cell key={i} fill={d.fill} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </ChartPanel>
      <ChartPanel title={CL.adSalesShare} delayMs={140} height="h-auto min-h-[240px]">
        <div style={{ height: chartH }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={adShareData} layout="vertical" margin={{ left: 4, right: 16, top: 4, bottom: 4 }}>
              <CartesianGrid {...CHART_CARTESIAN_GRID} horizontal={false} />
              <XAxis type="number" domain={[0, 100]} {...CHART_X_AXIS} unit="%" tick={{ fontSize: 10 }} />
              <YAxis type="category" dataKey="name" {...CHART_Y_AXIS} width={80} interval={0} tick={{ fontSize: 10 }} />
              <Tooltip {...competitorBarTooltipProps({ content: <CompetitorChartTooltip valueFormatter={(v) => formatPctPoints(v)} /> })} />
              <Bar dataKey="value" name={CL.adSalesShare} radius={[0, 3, 3, 0]}>
                {adShareData.map((d, i) => (
                  <Cell key={i} fill={d!.fill} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </ChartPanel>
    </div>
  );

  const rentChart = rentData.length > 0 && (
    <ChartPanel title={CL.rentPerCap} delayMs={100} height="h-auto min-h-[240px]">
      <div style={{ height: chartH }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rentData} layout="vertical" margin={{ left: 4, right: 16, top: 4, bottom: 4 }}>
            <CartesianGrid {...CHART_CARTESIAN_GRID} horizontal={false} />
            <XAxis type="number" {...CHART_X_AXIS} tick={{ fontSize: 10 }} />
            <YAxis type="category" dataKey="name" {...CHART_Y_AXIS} width={80} interval={0} tick={{ fontSize: 10 }} />
            <Tooltip {...competitorBarTooltipProps({ content: <CompetitorChartTooltip valueFormatter={(v) => `${formatDecimal2(v)} ${CL.unitYuan}`} /> })} />
            <Bar dataKey="value" name={CL.rentPerCap} radius={[0, 3, 3, 0]}>
              {rentData.map((d, i) => (
                <Cell key={i} fill={d.fill} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </ChartPanel>
  );

  const fxChart = fxMixData.length > 0 && (
    <ChartPanel title={CL.currencyMix} delayMs={100} height="h-auto min-h-[240px]">
      <div style={{ height: chartH }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={fxMixData} layout="vertical" margin={{ left: 4, right: 16, top: 4, bottom: 4 }}>
            <CartesianGrid {...CHART_CARTESIAN_GRID} horizontal={false} />
            <XAxis type="number" domain={[0, 100]} {...CHART_X_AXIS} unit="%" tick={{ fontSize: 10 }} />
            <YAxis type="category" dataKey="name" {...CHART_Y_AXIS} width={80} interval={0} tick={{ fontSize: 10 }} />
            <Tooltip {...competitorBarTooltipProps({ content: <CompetitorChartTooltip valueFormatter={(v) => formatPctPoints(v)} /> })} />
            <Legend wrapperStyle={{ fontSize: 10 }} />
            <Bar dataKey="rmb" name={CL.rmbShare} stackId="fx" fill={BUSINESS_CHART_COLORS.actual} />
            <Bar dataKey="fx" name={CL.fxShare} stackId="fx" fill="#d97706" />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </ChartPanel>
  );

  const arChart = arOver1y.length > 0 && (
    <ChartPanel title={CL.arAgingStruct} delayMs={100} height="h-auto min-h-[220px]">
      <div style={{ height: Math.max(200, arOver1y.length * 36 + 48) }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={arOver1y} layout="vertical" margin={{ left: 4, right: 16, top: 4, bottom: 4 }}>
            <CartesianGrid {...CHART_CARTESIAN_GRID} horizontal={false} />
            <XAxis type="number" domain={[0, 100]} {...CHART_X_AXIS} unit="%" tick={{ fontSize: 10 }} />
            <YAxis type="category" dataKey="name" {...CHART_Y_AXIS} width={88} interval={0} tick={{ fontSize: 9 }} />
            <Tooltip {...competitorBarTooltipProps({ content: <CompetitorChartTooltip valueFormatter={(v) => formatPctPoints(v)} /> })} />
            <Bar dataKey="value" name={CL.arOver1yShare} fill="#d97706" radius={[0, 3, 3, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </ChartPanel>
  );

  return (
    <ChapterPanel
      sectionId="sec-09"
      slides={[
        {
          id: "sec-09-a",
          title: subTitleForSnap("sec-09-a"),
          content: (
            <AnchorSlide
              insights={rentInsights}
              table={rent}
              tableTitle={CL.rentOffice}
              narrativeAnchor="sec-09-1"
              blocks={blocks}
              chart={rentChart}
            />
          ),
        },
        {
          id: "sec-09-b",
          title: subTitleForSnap("sec-09-b"),
          content: (
            <AnchorSlide
              insights={roiInsights}
              table={roi}
              tableTitle={CL.roiAds}
              narrativeAnchor="sec-09-2"
              blocks={blocks}
              chart={roiCharts}
            />
          ),
        },
        {
          id: "sec-09-c",
          title: subTitleForSnap("sec-09-c"),
          content: (
            <AnchorSlide insights={govInsights} table={gov} tableTitle={CL.govSubsidy} narrativeAnchor="sec-09-3" blocks={blocks} />
          ),
        },
        {
          id: "sec-09-d",
          title: subTitleForSnap("sec-09-d"),
          content: (
            <AnchorSlide
              insights={pipeInsights}
              table={rndProjects}
              tableTitle={CL.rndPipeline}
              narrativeAnchor="sec-09-4"
              blocks={blocks}
              dense
            />
          ),
        },
        {
          id: "sec-09-e",
          title: subTitleForSnap("sec-09-e"),
          content: dividend ? (
            <DataTable title={CL.shareholderDiv} headers={dividend.headers} rows={dividend.rows} delayMs={40} compact />
          ) : null,
        },
        {
          id: "sec-09-f",
          title: subTitleForSnap("sec-09-f"),
          content: (
            <AnchorSlide
              insights={fxInsights}
              table={currency}
              tableTitle={CL.currencyMix}
              narrativeAnchor="sec-09-6"
              blocks={blocks}
              chart={fxChart}
            />
          ),
        },
        {
          id: "sec-09-g",
          title: subTitleForSnap("sec-09-g"),
          content: (
            <AnchorSlide
              insights={invInsights}
              table={investment}
              tableTitle={CL.investmentAlloc}
              narrativeAnchor="sec-09-7"
              blocks={blocks}
            />
          ),
        },
        {
          id: "sec-09-h",
          title: subTitleForSnap("sec-09-h"),
          content: (
            <AnchorSlide
              insights={arInsights}
              table={arAging}
              tableTitle={CL.arAgingStruct}
              narrativeAnchor="sec-09-8"
              blocks={blocks}
              chart={arChart}
            />
          ),
        },
        {
          id: "sec-09-i",
          title: subTitleForSnap("sec-09-i"),
          content: (
            <AnchorSlide
              insights={prodInsights}
              table={products}
              tableTitle={CL.operatingProducts}
              narrativeAnchor="sec-09-9"
              blocks={blocks}
              dense
            />
          ),
        },
      ]}
    />
  );
}
