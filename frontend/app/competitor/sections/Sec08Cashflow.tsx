"use client";

import type { ReactNode } from "react";
import { useMemo } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { CashQualityMatrix } from "../components/CashQualityMatrix";
import { ChapterPanel } from "../components/ChapterPanel";
import { ChartPanel } from "../components/ChartPanel";
import { CompetitorChartTooltip, competitorBarTooltipProps } from "../components/CompetitorChartTooltip";
import { DataTable } from "../components/DataTable";
import { SubjectAnalysisBoard } from "../components/SubjectAnalysisBoard";
import { BUSINESS_CHART_COLORS } from "../../lib/business_chart_colors";
import { CHART_CARTESIAN_GRID, CHART_X_AXIS, CHART_Y_AXIS } from "../lib/competitor_chart_colors";
import { COMPANY_COLS, colToLabel, rowValueForCompany } from "../lib/companies";
import { parseCashQualityPoints } from "../lib/finance_analysis";
import { CL, FK, FK_CF_ITEM } from "../lib/field_keys";
import {
  cfProfitRatioToPercentPoints,
  formatDecimal2,
  formatPctPoints,
  formatTableCell,
  parseNum,
  toPercentPoints,
} from "../lib/format";
import { hasMarkdownBold, renderBoldMarkdown, stripMarkdownBold } from "../lib/markdown_bold";
import { subTitleForSnap } from "../lib/navigation";
import { buildCashSubjectGroups } from "../lib/profit_subject_analysis";
import { getTable } from "../lib/selectors";
import { type SectionProps } from "../lib/section_ui";

function narrativeMarkdown(blocks: SectionProps["snapshot"]["sections"][0]["blocks"], anchor: string): string {
  const hit = blocks.find((b) => b.kind === "narrative" && b.anchor === anchor);
  if (!hit || hit.kind !== "narrative") return "";
  return hit.markdown?.trim() ?? "";
}

function formatCfItemsCell(header: string, value: string | number | null): ReactNode {
  const raw = value == null ? "" : String(value);
  const plain = stripMarkdownBold(raw);
  const formatted = formatTableCell(header, plain);

  if (header === FK_CF_ITEM && hasMarkdownBold(raw)) {
    return renderBoldMarkdown(raw);
  }
  if (hasMarkdownBold(raw)) {
    return <strong className="font-semibold text-zinc-100">{formatted}</strong>;
  }
  return formatted;
}

function formatCfQualityCell(
  header: string,
  value: string | number | null,
  row?: Record<string, string | number | null>,
): ReactNode {
  const metric = stripMarkdownBold(String(row?.[FK.metric] ?? ""));

  if (header === FK.metric) {
    const raw = value == null ? "" : String(value);
    return hasMarkdownBold(raw) ? renderBoldMarkdown(raw) : raw || "—";
  }

  const n = parseNum(value);
  if (n == null) {
    if (value == null || value === "") return "—";
    const raw = String(value);
    return hasMarkdownBold(raw) ? renderBoldMarkdown(raw) : raw;
  }

  if (/经营.*(CF|现金流)\/净利/.test(metric)) {
    return formatPctPoints(cfProfitRatioToPercentPoints(n));
  }
  if (metric.includes("增长率")) {
    return formatPctPoints(toPercentPoints(n));
  }
  if (metric.includes("销售收现比")) {
    return formatDecimal2(n);
  }
  return formatTableCell(header, n);
}

export function Sec08Cashflow({ snapshot }: SectionProps) {
  const cfItems = getTable(snapshot, "sec-08-1");
  const cfQuality = getTable(snapshot, "sec-08-2");

  const qualityPoints = useMemo(() => parseCashQualityPoints(snapshot), [snapshot]);

  const cashAnalysisMarkdown = useMemo(() => {
    const secBlocks = snapshot.sections.find((s) => s.id === "sec-08")?.blocks ?? [];
    return narrativeMarkdown(secBlocks, "sec-08-2");
  }, [snapshot]);
  const cashSubjectGroups = useMemo(
    () => buildCashSubjectGroups(cashAnalysisMarkdown),
    [cashAnalysisMarkdown],
  );

  const profitRow = cfQuality?.rows.find((r) => String(r[FK.metric] ?? "").includes(CL.netProfit));
  const ocfRow = cfQuality?.rows.find((r) => /经营.*(CF|现金流)/.test(String(r[FK.metric] ?? "")));

  const compareData = useMemo(
    () =>
      COMPANY_COLS.map((col) => {
        const profit = profitRow ? parseNum(rowValueForCompany(profitRow, col)) : null;
        const ocf = ocfRow ? parseNum(rowValueForCompany(ocfRow, col)) : null;
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

  const chartH = Math.max(280, compareData.length * 44 + 72);

  return (
    <ChapterPanel
      sectionId="sec-08"
      slides={[
        {
          id: "sec-08-a",
          title: subTitleForSnap("sec-08-a"),
          dense: true,
          content: (
            <>
              {cfItems ? (
                <DataTable
                  title={CL.cfItems}
                  headers={cfItems.headers}
                  rows={cfItems.rows}
                  delayMs={40}
                  compact
                  formatCell={formatCfItemsCell}
                />
              ) : null}
              {cfQuality ? (
                <div className="mt-5 sm:mt-6">
                  <DataTable
                    title={CL.profitVsOcf}
                    headers={cfQuality.headers}
                    rows={cfQuality.rows}
                    delayMs={60}
                    compact
                    formatCell={formatCfQualityCell}
                  />
                </div>
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
                        <Tooltip {...competitorBarTooltipProps({ content: <CompetitorChartTooltip valueFormatter={(v) => formatDecimal2(v)} /> })} />
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
              <SubjectAnalysisBoard groups={cashSubjectGroups} snapshot={snapshot} delayMs={180} />
            </>
          ),
        },
      ]}
    />
  );
}
