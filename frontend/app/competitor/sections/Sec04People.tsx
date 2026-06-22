"use client";

import type { ReactNode } from "react";
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
import { AppleFocusExplorer } from "../components/AppleFocusExplorer";
import { ChapterPanel } from "../components/ChapterPanel";
import { CompetitorChartTooltip, competitorBarTooltipProps } from "../components/CompetitorChartTooltip";
import { DataTable } from "../components/DataTable";
import { NarrativesFromSection } from "../components/NarrativeBlock";
import { BUSINESS_CHART_COLORS } from "../../lib/business_chart_colors";
import {
  CHART_CARTESIAN_GRID,
  CHART_X_AXIS,
  CHART_Y_AXIS,
  colorForCompany,
} from "../lib/competitor_chart_colors";
import { companyColsForSnapshot, colToLabel, companyDisplayLabel, rowValueForCompany } from "../lib/companies";
import { CL, FK } from "../lib/field_keys";
import { formatDecimal2, formatPctPoints, formatTableCell, parseNum, toPercentPoints } from "../lib/format";
import { LaborCostTable } from "../components/LaborCostTable";
import { laborCostTableHasFullSections } from "../lib/labor_cost_table_utils";
import { subTitleForSnap } from "../lib/navigation";
import { getBestTable } from "../lib/selectors";
import { type SectionProps } from "../lib/section_ui";

const STACK_SERIES = [
  { key: "rd", label: CL.rdShort, color: BUSINESS_CHART_COLORS.current },
  { key: "ops", label: FK.opsSales, color: BUSINESS_CHART_COLORS.actual },
  { key: "adm", label: FK.adminFinance, color: BUSINESS_CHART_COLORS.lastYear },
] as const;

const METRIC_HEADCOUNT_CHANGE = "\u589e\u51cf\u53d8\u52a8";
const METRIC_HEADCOUNT_AMP = "\u589e\u51cf\u5e45\u5ea6";

function formatAmplitudePct(val: string | number | null | undefined): string {
  if (val == null || val === "") return "\u2014";
  if (typeof val === "string") {
    const t = val.trim();
    if (t.endsWith("%")) return t;
  }
  const n = parseNum(val);
  if (n == null) return typeof val === "string" ? val : "\u2014";
  const pct = toPercentPoints(n);
  const sign = pct > 0 ? "+" : "";
  return `${sign}${pct.toFixed(1)}%`;
}

function headcountTableRows(rows: Record<string, string | number | null>[]) {
  return rows.filter((row) => String(row[FK.metric] ?? "") !== METRIC_HEADCOUNT_CHANGE);
}

function headcountFormatCell(
  header: string,
  val: string | number | null,
  row?: Record<string, string | number | null>,
) {
  if (String(row?.[FK.metric] ?? "") === METRIC_HEADCOUNT_AMP && header !== FK.metric) {
    return formatAmplitudePct(val);
  }
  return formatTableCell(header, val);
}

function PanelChart({
  children,
  caption,
  chartClassName = "h-44 w-full sm:h-48",
}: {
  children: ReactNode;
  caption?: string;
  chartClassName?: string;
}) {
  return (
    <div className="flex w-full flex-col">
      {caption ? <p className="mb-2 text-sm font-medium text-zinc-300">{caption}</p> : null}
      <div className={chartClassName}>{children}</div>
    </div>
  );
}

function TopicStack({ children }: { children: ReactNode }) {
  return <div className="space-y-4 sm:space-y-5">{children}</div>;
}

function findEfficiencyRow(
  rows: Record<string, string | number | null>[] | undefined,
  exactLabel: string,
) {
  return rows?.find((r) => String(r[FK.metric] ?? "") === exactLabel);
}

function findPerCapRevRow(rows: Record<string, string | number | null>[] | undefined) {
  return (
    findEfficiencyRow(rows, "\u4eba\u5747\u521b\u6536(\u4e07)") ??
    rows?.find((r) => {
      const m = String(r[FK.metric] ?? "");
      return m.includes("\u4eba\u5747\u521b\u6536") && !m.includes("\u4e0a\u5e74") && !m.includes("\u53d8\u52a8");
    })
  );
}

function findPerCapProfitRow(rows: Record<string, string | number | null>[] | undefined) {
  return (
    findEfficiencyRow(rows, "\u4eba\u5747\u521b\u5229(\u4e07)") ??
    rows?.find((r) => {
      const m = String(r[FK.metric] ?? "");
      return m.includes("\u4eba\u5747\u521b\u5229") && !m.includes("\u4e0a\u5e74") && !m.includes("\u53d8\u52a8");
    })
  );
}

function buildMetricBarData(
  metricRow: Record<string, string | number | null> | undefined,
  snapshot: SectionProps["snapshot"],
  tableHeaders?: string[],
) {
  if (!metricRow) return [];
  const cols = companyColsForSnapshot(snapshot, tableHeaders);
  return cols.map((col) => {
    const value = parseNum(rowValueForCompany(metricRow, col));
    if (value == null) return null;
    return {
      name: colToLabel(col, snapshot),
      colKey: col,
      value,
    };
  }).filter(Boolean);
}

function buildHeadcountAmpData(
  rows: Record<string, string | number | null>[] | undefined,
  snapshot: SectionProps["snapshot"],
  tableHeaders?: string[],
) {
  const ampRow = rows?.find((r) => String(r[FK.metric] ?? "") === METRIC_HEADCOUNT_AMP);
  if (!ampRow) return [];
  const cols = companyColsForSnapshot(snapshot, tableHeaders);
  return cols.map((col) => {
    const raw = rowValueForCompany(ampRow, col);
    const n = parseNum(raw);
    if (n == null) return null;
    const pct = toPercentPoints(n);
    return {
      name: colToLabel(col, snapshot),
      colKey: col,
      value: pct,
    };
  }).filter(Boolean);
}

export function Sec04People({ snapshot }: SectionProps) {
  const sec04 = snapshot.sections.find((s) => s.id === "sec-04");
  const blocks = sec04?.blocks ?? [];
  const headcount = getBestTable(snapshot, "sec-04-1");
  const efficiency = getBestTable(snapshot, "sec-04-2");
  const laborCost = getBestTable(snapshot, "sec-04-3");
  const structure = getBestTable(snapshot, "sec-04-4");

  const stackData =
    structure?.rows
      .map((row) => {
        const name = String(row[FK.company] ?? "");
        const rd = parseNum(row[FK.rdStaff]) ?? 0;
        const ops = parseNum(row[FK.opsSales]) ?? 0;
        const adm = parseNum(row[FK.adminFinance]) ?? 0;
        const total = rd + ops + adm;
        if (!name || total <= 0) return null;
        return {
          name: companyDisplayLabel(name, snapshot),
          rd: (rd / total) * 100,
          ops: (ops / total) * 100,
          adm: (adm / total) * 100,
        };
      })
      .filter(Boolean) ?? [];

  const revRow = findPerCapRevRow(efficiency?.rows);
  const profRow = findPerCapProfitRow(efficiency?.rows);

  const perCapRevData = buildMetricBarData(revRow, snapshot, efficiency?.headers);
  const perCapProfitData = buildMetricBarData(profRow, snapshot, efficiency?.headers);
  const headcountAmpData = buildHeadcountAmpData(headcount?.rows, snapshot, headcount?.headers);

  const headcountAmpChart = (
    <PanelChart caption={CL.headcountAmpChart} chartClassName="h-60 w-full sm:h-72">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={headcountAmpData}
          layout="vertical"
          margin={{ left: 4, right: 12, top: 4, bottom: 4 }}
          barCategoryGap="16%"
        >
          <CartesianGrid {...CHART_CARTESIAN_GRID} horizontal={false} />
          <XAxis
            type="number"
            {...CHART_X_AXIS}
            tickFormatter={(v) => `${v > 0 ? "+" : ""}${v.toFixed(1)}%`}
            tick={{ fontSize: 10 }}
          />
          <YAxis type="category" dataKey="name" {...CHART_Y_AXIS} width={80} tick={{ fontSize: 10 }} interval={0} />
          <Tooltip
            {...competitorBarTooltipProps({
              content: (
                <CompetitorChartTooltip valueFormatter={(v) => `${Number(v) > 0 ? "+" : ""}${Number(v).toFixed(1)}%`} />
              ),
            })}
          />
          <Legend wrapperStyle={{ fontSize: 10 }} />
          <Bar dataKey="value" name={METRIC_HEADCOUNT_AMP} radius={[0, 3, 3, 0]}>
            {headcountAmpData.map((d, i) => (
              <Cell
                key={i}
                fill={d!.value >= 0 ? BUSINESS_CHART_COLORS.actual : "#ef4444"}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </PanelChart>
  );

  const structureChart = (
    <PanelChart caption={CL.staffStructureShare}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={stackData} layout="vertical" margin={{ left: 4, right: 8, top: 0, bottom: 0 }}>
          <CartesianGrid {...CHART_CARTESIAN_GRID} horizontal={false} />
          <XAxis type="number" domain={[0, 100]} {...CHART_X_AXIS} unit="%" tick={{ fontSize: 10 }} />
          <YAxis type="category" dataKey="name" {...CHART_Y_AXIS} width={68} tick={{ fontSize: 10 }} />
          <Tooltip {...competitorBarTooltipProps({ content: <CompetitorChartTooltip valueFormatter={(v) => formatPctPoints(v)} /> })} />
          <Legend wrapperStyle={{ fontSize: 10 }} />
          {STACK_SERIES.map(({ key, label, color }) => (
            <Bar key={key} dataKey={key} name={label} stackId="staff" fill={color} fillOpacity={0.9} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </PanelChart>
  );

  const perCapRevChart = (
    <PanelChart caption={CL.perCapRevChart} chartClassName="h-60 w-full sm:h-72">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={perCapRevData}
          layout="vertical"
          margin={{ left: 4, right: 12, top: 4, bottom: 4 }}
          barCategoryGap="16%"
        >
          <CartesianGrid {...CHART_CARTESIAN_GRID} horizontal={false} />
          <XAxis type="number" {...CHART_X_AXIS} tickFormatter={(v) => formatDecimal2(v)} tick={{ fontSize: 10 }} />
          <YAxis type="category" dataKey="name" {...CHART_Y_AXIS} width={80} tick={{ fontSize: 10 }} interval={0} />
          <Tooltip
            {...competitorBarTooltipProps({
              content: <CompetitorChartTooltip valueFormatter={(v) => formatDecimal2(v)} />,
            })}
          />
          <Legend wrapperStyle={{ fontSize: 10 }} />
          <Bar dataKey="value" name={CL.perCapRevAxis} radius={[0, 3, 3, 0]}>
            {perCapRevData.map((d, i) => (
              <Cell key={i} fill={colorForCompany(d!.colKey, snapshot)} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </PanelChart>
  );

  const perCapProfitChart = (
    <PanelChart caption={CL.perCapProfitChart} chartClassName="h-60 w-full sm:h-72">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={perCapProfitData}
          layout="vertical"
          margin={{ left: 4, right: 12, top: 4, bottom: 4 }}
          barCategoryGap="16%"
        >
          <CartesianGrid {...CHART_CARTESIAN_GRID} horizontal={false} />
          <XAxis type="number" {...CHART_X_AXIS} tickFormatter={(v) => formatDecimal2(v)} tick={{ fontSize: 10 }} />
          <YAxis type="category" dataKey="name" {...CHART_Y_AXIS} width={80} tick={{ fontSize: 10 }} interval={0} />
          <Tooltip
            {...competitorBarTooltipProps({
              content: <CompetitorChartTooltip valueFormatter={(v) => formatDecimal2(v)} />,
            })}
          />
          <Legend wrapperStyle={{ fontSize: 10 }} />
          <Bar dataKey="value" name={CL.perCapProfitAxis} radius={[0, 3, 3, 0]}>
            {perCapProfitData.map((d, i) => (
              <Cell key={i} fill={colorForCompany(d!.colKey, snapshot)} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </PanelChart>
  );

  const headcountTable =
    headcount?.rows && headcount.rows.length > 0 ? (
      <DataTable
        headers={headcount.headers}
        rows={headcountTableRows(headcount.rows)}
        delayMs={0}
        compact
        formatCell={headcountFormatCell}
      />
    ) : null;

  const efficiencyTable =
    efficiency?.rows && efficiency.rows.length > 0 ? (
      <DataTable headers={efficiency.headers} rows={efficiency.rows} delayMs={0} compact />
    ) : null;

  const laborTable =
    laborCost?.rows && laborCost.rows.length > 0 ? (
      <LaborCostTable table={laborCost} snapshot={snapshot} />
    ) : null;

  const laborCostIncomplete =
    laborCost?.rows && laborCost.rows.length > 0 && !laborCostTableHasFullSections(laborCost.rows);

  const structureTable =
    structure?.rows && structure.rows.length > 0 ? (
      <DataTable headers={structure.headers} rows={structure.rows} delayMs={0} compact />
    ) : null;

  const explorerTopics = [
    ...(headcountTable
      ? [
          {
            id: "headcount",
            title: CL.headcount,
            content: (
              <TopicStack>
                {headcountTable}
                {headcountAmpData.length > 0 ? headcountAmpChart : null}
                <NarrativesFromSection blocks={blocks} anchor="sec-04-1" immediate plain stripAnalysisPrefix />
              </TopicStack>
            ),
          },
        ]
      : []),
    {
      id: "efficiency",
      title: CL.efficiencyMetrics,
      content: (
        <TopicStack>
          {efficiencyTable}
          <div className="grid gap-4 lg:grid-cols-2">
            {perCapRevChart}
            {perCapProfitChart}
          </div>
          <NarrativesFromSection blocks={blocks} anchor="sec-04-2" immediate plain stripAnalysisPrefix />
        </TopicStack>
      ),
    },
    ...(laborTable
      ? [
          {
            id: "labor",
            title: CL.laborCost,
            content: (
              <TopicStack>
                {laborCostIncomplete ? (
                  <p className="text-xs leading-relaxed text-amber-400/90">
                    当前快照缺少「职工福利 / 工会经费」分组，请在财务后台重新上传蓝本（直接改仓库 MD 不会自动生效）。
                  </p>
                ) : null}
                {laborTable}
                <NarrativesFromSection blocks={blocks} anchor="sec-04-3" immediate plain stripAnalysisPrefix />
              </TopicStack>
            ),
          },
        ]
      : []),
    {
      id: "structure",
      title: CL.staffStructure,
      content: (
        <TopicStack>
          {structureChart}
          {structureTable}
          <NarrativesFromSection blocks={blocks} anchor="sec-04-4" immediate plain stripAnalysisPrefix />
        </TopicStack>
      ),
    },
  ];

  return (
    <ChapterPanel
      sectionId="sec-04"
      slides={[
        {
          id: "sec-04-a",
          title: subTitleForSnap("sec-04-a"),
          dense: true,
          content: <AppleFocusExplorer defaultActiveId="headcount" topics={explorerTopics} />,
        },
      ]}
    />
  );
}
