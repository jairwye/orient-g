"use client";

import { useMemo } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  LabelList,
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
import { NarrativesFromSection } from "../components/NarrativeBlock";
import { BUSINESS_CHART_COLORS } from "../../lib/business_chart_colors";
import { CHART_CARTESIAN_GRID, CHART_X_AXIS, CHART_Y_AXIS } from "../lib/competitor_chart_colors";
import { companyDisplayLabel } from "../lib/companies";
import { CL, FK } from "../lib/field_keys";
import { formatPctPoints, parseNum } from "../lib/format";
import { sec05PercentPoints } from "../lib/sec05_product";
import { subTitleForSnap } from "../lib/navigation";
import { getTable } from "../lib/selectors";
import { type SectionProps } from "../lib/section_ui";

const REV_SHARE = "\u6536\u5165\u5360\u6bd4";
const REGION_DOMESTIC = "\u5883\u5185";
const REGION_OVERSEAS = "\u5883\u5916";

const REGION_COLORS: Record<string, string> = {
  [REGION_DOMESTIC]: BUSINESS_CHART_COLORS.current,
  [REGION_OVERSEAS]: BUSINESS_CHART_COLORS.actual,
};

type RegionRow = Record<string, string | number | null>;

function isValidRegionRow(row: RegionRow): boolean {
  const region = String(row[FK.region] ?? "").trim();
  if (!region || region === "\u2014" || region === "-") return false;
  return parseNum(row[REV_SHARE]) != null;
}

function normalizeShare(raw: number): number {
  return sec05PercentPoints(raw);
}

function buildRegionMix(rows: RegionRow[], snapshot: SectionProps["snapshot"]) {
  const regions = new Set<string>();
  const byCompany = new Map<string, { name: string; segments: Record<string, number> }>();

  for (const row of rows) {
    if (!isValidRegionRow(row)) continue;
    const company = String(row[FK.company] ?? "");
    const region = String(row[FK.region] ?? "").trim();
    const shareRaw = parseNum(row[REV_SHARE]);
    if (!company || !region || shareRaw == null) continue;
    regions.add(region);
    if (!byCompany.has(company)) {
      byCompany.set(company, { name: companyDisplayLabel(company, snapshot), segments: {} });
    }
    const share = normalizeShare(shareRaw);
    byCompany.get(company)!.segments[region] = (byCompany.get(company)!.segments[region] ?? 0) + share;
  }

  const regionOrder = [REGION_DOMESTIC, REGION_OVERSEAS];
  const types = [
    ...regionOrder.filter((r) => regions.has(r)),
    ...[...regions].filter((r) => !regionOrder.includes(r)).sort((a, b) => a.localeCompare(b, "zh-CN")),
  ];
  const data = [...byCompany.values()].map(({ name, segments }) => {
    const item: Record<string, string | number> = { name };
    for (const r of types) item[r] = segments[r] ?? 0;
    return item;
  });

  return { types, data };
}

export function Sec05Region({ snapshot }: SectionProps) {
  const sec05 = snapshot.sections.find((s) => s.id === "sec-05");
  const regionTable = getTable(snapshot, "sec-05-2");

  const tableRows = useMemo(
    () => (regionTable?.rows ?? []).filter(isValidRegionRow),
    [regionTable?.rows],
  );

  const { types, data: mixData } = useMemo(
    () => buildRegionMix(regionTable?.rows ?? [], snapshot),
    [regionTable?.rows, snapshot],
  );

  const chartHeight = Math.max(280, mixData.length * 40 + 80);

  if (!regionTable?.rows?.length) return null;

  return (
    <ChapterPanel
      sectionId="sec-05"
      slides={[
        {
          id: "sec-05-b",
          title: subTitleForSnap("sec-05-b"),
          dense: true,
          subOnly: true,
          content: (
            <>
              <ChartPanel title={CL.regionRevenueShare} height="h-auto" delayMs={60}>
                <div style={{ height: chartHeight }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={mixData}
                      layout="vertical"
                      margin={{ left: 4, right: 24, top: 4, bottom: 28 }}
                      barCategoryGap="16%"
                    >
                      <CartesianGrid {...CHART_CARTESIAN_GRID} horizontal={false} />
                      <XAxis type="number" domain={[0, 100]} {...CHART_X_AXIS} unit="%" tick={{ fontSize: 10 }} />
                      <YAxis type="category" dataKey="name" {...CHART_Y_AXIS} width={80} tick={{ fontSize: 10 }} interval={0} />
                      <Tooltip {...competitorBarTooltipProps({ content: <CompetitorChartTooltip valueFormatter={(v) => formatPctPoints(v)} /> })} />
                      <Legend wrapperStyle={{ fontSize: 10 }} verticalAlign="bottom" />
                      {types.map((region) => (
                        <Bar
                          key={region}
                          dataKey={region}
                          name={region}
                          stackId="region"
                          fill={REGION_COLORS[region] ?? "#71717a"}
                          fillOpacity={0.92}
                        >
                          <LabelList
                            dataKey={region}
                            position="center"
                            formatter={(v: number) => (v >= 10 ? formatPctPoints(v) : "")}
                            fill="#f4f4f5"
                            fontSize={9}
                            style={{ pointerEvents: "none" }}
                          />
                        </Bar>
                      ))}
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </ChartPanel>

              {tableRows.length > 0 ? (
                <div className="mt-4">
                  <DataTable
                    headers={regionTable.headers}
                    rows={tableRows}
                    delayMs={80}
                    compact
                  />
                </div>
              ) : null}

              <div className="mt-3 text-sm leading-relaxed text-zinc-400">
                <NarrativesFromSection
                  blocks={sec05?.blocks ?? []}
                  anchor="sec-05-2"
                  plain
                  stripAnalysisPrefix
                />
              </div>
            </>
          ),
        },
      ]}
    />
  );
}
