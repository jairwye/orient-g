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
import { ChapterPanel } from "../components/ChapterPanel";
import { ChartPanel } from "../components/ChartPanel";
import { CompetitorChartTooltip, competitorBarTooltipProps } from "../components/CompetitorChartTooltip";
import { DataTable } from "../components/DataTable";
import { DivergingBarPanel } from "../components/DivergingBarPanel";
import { SubjectAnalysisBoard } from "../components/SubjectAnalysisBoard";
import { BUSINESS_CHART_COLORS } from "../../lib/business_chart_colors";
import {
  CHART_CARTESIAN_GRID,
  CHART_X_AXIS,
  CHART_Y_AXIS,
  colorForCompany,
} from "../lib/competitor_chart_colors";
import { companyColsForSnapshot, colToLabel, competitorTableUiProps, rowValueForCompany } from "../lib/companies";
import { CL, FK, FK_AMOUNT_CHANGE } from "../lib/field_keys";
import { formatPctPoints, parseNum, toPercentPoints } from "../lib/format";
import { subTitleForSnap } from "../lib/navigation";
import { buildFeeSubjectGroups, buildProfitSubjectGroups } from "../lib/profit_subject_analysis";
import { getTable } from "../lib/selectors";
import { type SectionProps } from "../lib/section_ui";

const FEE_STACK = [
  { key: FK.salesFeeRate, color: BUSINESS_CHART_COLORS.current },
  { key: FK.adminFeeRate, color: "#d97706" },
  { key: FK.rndFeeRate, color: "#7c3aed" },
] as const;

const FEE_CHANGE_METRICS = [FK.grossMarginRate, FK.salesFeeRate, FK.adminFeeRate, FK.rndFeeRate] as const;

const FEE_AMOUNT_ROWS = ["营业成本", "销售费用", "管理费用", "研发费用"] as const;

function pctPoints(v: number | null): number | null {
  if (v == null) return null;
  return toPercentPoints(v);
}

function deltaFill(metric: string, delta: number): string {
  const isFee = metric !== FK.grossMarginRate;
  if (isFee) return delta <= 0 ? BUSINESS_CHART_COLORS.actual : "#ef4444";
  return delta >= 0 ? BUSINESS_CHART_COLORS.actual : "#ef4444";
}

function narrativeMarkdown(blocks: SectionProps["snapshot"]["sections"][0]["blocks"], anchor: string): string {
  const hit = blocks.find((b) => b.kind === "narrative" && b.anchor === anchor);
  if (!hit || hit.kind !== "narrative") return "";
  return hit.markdown?.trim() ?? "";
}

function buildAmountChangeBars(
  table: ReturnType<typeof getTable>,
  subject: string,
  snapshot: SectionProps["snapshot"],
) {
  const row = table?.rows.find((r) => String(r[FK_AMOUNT_CHANGE] ?? "") === subject);
  if (!row) return [];
  const cols = companyColsForSnapshot(snapshot, table?.headers);
  return cols.map((col) => {
    const delta = parseNum(rowValueForCompany(row, col));
    if (delta == null) return null;
    const isCostLike = subject === "销售费用" || subject === "管理费用" || subject === "研发费用" || subject === "营业成本";
    const good = isCostLike ? delta <= 0 : delta >= 0;
    return {
      name: colToLabel(col, snapshot),
      delta,
      fill: good ? BUSINESS_CHART_COLORS.actual : "#ef4444",
    };
  })
    .filter(Boolean)
    .sort((a, b) => b!.delta - a!.delta) as Array<{ name: string; delta: number; fill: string }>;
}

export function Sec07Profit({ snapshot }: SectionProps) {
  const core = getTable(snapshot, "sec-07-1");
  const drivers = getTable(snapshot, "sec-07-2");
  const fees = getTable(snapshot, "sec-07-3");
  const feePctChg = getTable(snapshot, "sec-07-4");
  const feeAmtChg = getTable(snapshot, "sec-07-5");

  const profitAnalysisMarkdown = useMemo(() => {
    const secBlocks = snapshot.sections.find((s) => s.id === "sec-07")?.blocks ?? [];
    return narrativeMarkdown(secBlocks, "sec-07-1");
  }, [snapshot]);
  const profitSubjectGroups = useMemo(
    () => buildProfitSubjectGroups(profitAnalysisMarkdown, drivers, snapshot),
    [profitAnalysisMarkdown, drivers, snapshot],
  );

  const feeAnalysisMarkdown = useMemo(() => {
    const secBlocks = snapshot.sections.find((s) => s.id === "sec-07")?.blocks ?? [];
    return narrativeMarkdown(secBlocks, "sec-07-5");
  }, [snapshot]);
  const feeSubjectGroups = useMemo(
    () => buildFeeSubjectGroups(feeAnalysisMarkdown, snapshot),
    [feeAnalysisMarkdown, snapshot],
  );

  const feeCols = useMemo(
    () => companyColsForSnapshot(snapshot, fees?.headers ?? feePctChg?.headers),
    [snapshot, fees?.headers, feePctChg?.headers],
  );

  const feeStackData = useMemo(
    () =>
      feeCols.map((col) => {
        const point: Record<string, string | number> = { name: colToLabel(col, snapshot) };
        let hasAny = false;
        for (const { key } of FEE_STACK) {
          const row = fees?.rows.find((r) => String(r[FK.metric] ?? "") === key);
          const v = row ? pctPoints(parseNum(rowValueForCompany(row, col))) : null;
          if (v != null) {
            point[key] = v;
            hasAny = true;
          }
        }
        return hasAny ? point : null;
      }).filter(Boolean),
    [fees?.rows, feeCols, snapshot],
  );

  const grossMarginData = useMemo(
    () =>
      feeCols.map((col) => {
        const row = fees?.rows.find((r) => String(r[FK.metric] ?? "") === FK.grossMarginRate);
        const v = row ? pctPoints(parseNum(rowValueForCompany(row, col))) : null;
        if (v == null) return null;
        return { name: colToLabel(col, snapshot), value: v, fill: colorForCompany(col, snapshot) };
      })
        .filter(Boolean)
        .sort((a, b) => b!.value - a!.value),
    [fees?.rows, feeCols, snapshot],
  );

  const pctChangeCharts = useMemo(() => {
    if (!feePctChg?.rows.length) return [];
    const cols = companyColsForSnapshot(snapshot, feePctChg.headers);
    return FEE_CHANGE_METRICS.map((metric) => {
      const row = feePctChg.rows.find((r) => String(r[FK.changePct] ?? "") === metric);
      if (!row) return null;
      const data = cols.map((col) => {
        const raw = parseNum(rowValueForCompany(row, col));
        if (raw == null) return null;
        return { name: colToLabel(col, snapshot), delta: raw, fill: deltaFill(metric, raw) };
      })
        .filter(Boolean)
        .sort((a, b) => b!.delta - a!.delta);
      if (!data.length) return null;
      return { metric, data };
    }).filter(Boolean) as Array<{ metric: string; data: Array<{ name: string; delta: number; fill: string }> }>;
  }, [feePctChg?.rows, feePctChg?.headers, snapshot]);

  const amtChangeCharts = useMemo(
    () =>
      FEE_AMOUNT_ROWS.map((subject) => ({
        subject,
        data: buildAmountChangeBars(feeAmtChg, subject, snapshot),
      })).filter((x) => x.data.length > 0),
    [feeAmtChg, snapshot],
  );

  const chartH = Math.max(240, (feeStackData.length || 8) * 34 + 52);

  const feeRateCharts = (
    <div className="mt-5 grid gap-5 lg:grid-cols-2 lg:gap-6">
      <ChartPanel title={CL.grossMarginRank} delayMs={100} height="h-auto min-h-[220px]">
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
      <ChartPanel title={CL.feeStackHoriz} delayMs={140} height="h-auto min-h-[220px]">
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
  );

  const pctChangeBlock =
    pctChangeCharts.length > 0 ? (
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
    ) : null;

  const amtChangeBlock =
    amtChangeCharts.length > 0 ? (
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
    ) : null;

  return (
    <ChapterPanel
      sectionId="sec-07"
      slides={[
        {
          id: "sec-07-a",
          title: subTitleForSnap("sec-07-a"),
          content: (
            <>
              {core ? (
                <DataTable title={CL.profitCoreItems} headers={core.headers} rows={core.rows} delayMs={60} compact {...competitorTableUiProps(snapshot)} />
              ) : null}
              <SubjectAnalysisBoard groups={profitSubjectGroups} snapshot={snapshot} delayMs={100} />
            </>
          ),
        },
        {
          id: "sec-07-c",
          title: subTitleForSnap("sec-07-c"),
          dense: true,
          content: (
            <>
              {fees ? (
                <DataTable title={CL.feeRates} headers={fees.headers} rows={fees.rows} delayMs={40} compact {...competitorTableUiProps(snapshot)} />
              ) : null}
              {feeRateCharts}
              {feePctChg ? (
                <div className="mt-5 sm:mt-6">
                  <DataTable
                    title={CL.feeRateYoYTable}
                    headers={feePctChg.headers}
                    rows={feePctChg.rows}
                    delayMs={60}
                    compact
                    {...competitorTableUiProps(snapshot)}
                  />
                </div>
              ) : null}
              {pctChangeBlock}
              {feeAmtChg ? (
                <div className="mt-5 sm:mt-6">
                  <DataTable
                    title={CL.feeAmountYoY}
                    headers={feeAmtChg.headers}
                    rows={feeAmtChg.rows}
                    delayMs={80}
                    compact
                    {...competitorTableUiProps(snapshot)}
                  />
                </div>
              ) : null}
              {amtChangeBlock}
              <SubjectAnalysisBoard groups={feeSubjectGroups} snapshot={snapshot} delayMs={160} />
            </>
          ),
        },
      ]}
    />
  );
}
