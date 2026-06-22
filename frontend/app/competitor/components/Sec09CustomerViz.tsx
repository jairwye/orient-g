"use client";

import { useMemo } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ChartPanel } from "./ChartPanel";
import { CompetitorChartTooltip, competitorBarTooltipProps } from "./CompetitorChartTooltip";
import { CHART_CARTESIAN_GRID, CHART_X_AXIS, CHART_Y_AXIS, colorForCompany } from "../lib/competitor_chart_colors";
import { colToLabel, labelToCol } from "../lib/companies";
import { formatPctPoints, parseNum, sharePercentPoints } from "../lib/format";
import type { CustomerCompanyTable } from "../lib/sec09_customer_blocks";
import type { CompetitorReportSnapshot, TableBlock } from "../lib/types";

type SubjectTotal = { name: string; value: number; fill: string };

function sumTopFivePct(
  table: Pick<TableBlock, "rows">,
  match: (txType: string) => boolean,
): number {
  let total = 0;
  for (const row of table.rows) {
    const txType = String(row["往来类型"] ?? "");
    if (!match(txType)) continue;
    const raw = parseNum(row["占比"]);
    if (raw == null) continue;
    total += sharePercentPoints(raw);
  }
  return Math.round(total * 10) / 10;
}

function buildSubjectTotals(
  companyTables: CustomerCompanyTable[],
  snapshot: CompetitorReportSnapshot,
  kind: "customer" | "supplier",
): SubjectTotal[] {
  const match =
    kind === "customer"
      ? (tx: string) => tx.includes("前五客户")
      : (tx: string) => tx.includes("前五供应商");

  return companyTables
    .map(({ company, table }) => {
      const value = sumTopFivePct(table, match);
      if (value <= 0) return null;
      const name = colToLabel(company, snapshot);
      return {
        name,
        value,
        fill: colorForCompany(labelToCol(company) ?? company, snapshot),
      };
    })
    .filter(Boolean)
    .sort((a, b) => b!.value - a!.value) as SubjectTotal[];
}

function SubjectConcentrationChart({
  data,
  chartH,
  valueName,
}: {
  data: SubjectTotal[];
  chartH: number;
  valueName: string;
}) {
  return (
    <div style={{ height: chartH }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ left: 4, right: 16, top: 4, bottom: 4 }}>
          <CartesianGrid {...CHART_CARTESIAN_GRID} horizontal={false} />
          <XAxis type="number" domain={[0, "auto"]} {...CHART_X_AXIS} unit="%" tick={{ fontSize: 10 }} />
          <YAxis
            type="category"
            dataKey="name"
            {...CHART_Y_AXIS}
            width={80}
            interval={0}
            tick={{ fontSize: 10 }}
          />
          <Tooltip
            {...competitorBarTooltipProps({
              content: <CompetitorChartTooltip valueFormatter={(v) => formatPctPoints(v)} />,
            })}
          />
          <Bar dataKey="value" name={valueName} radius={[0, 3, 3, 0]}>
            {data.map((d, i) => (
              <Cell key={i} fill={d.fill} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

/** 重要客商：左右分图展示各主体前五客户 / 前五供应商合计占比 */
export function Sec09CustomerViz({
  companyTables,
  snapshot,
  delayMs = 80,
}: {
  companyTables: CustomerCompanyTable[];
  snapshot: CompetitorReportSnapshot;
  delayMs?: number;
}) {
  const customerData = useMemo(
    () => buildSubjectTotals(companyTables, snapshot, "customer"),
    [companyTables, snapshot],
  );
  const supplierData = useMemo(
    () => buildSubjectTotals(companyTables, snapshot, "supplier"),
    [companyTables, snapshot],
  );

  if (!customerData.length && !supplierData.length) return null;

  const rowCount = Math.max(customerData.length, supplierData.length, 1);
  const chartH = Math.max(220, rowCount * 40 + 56);

  return (
    <div className="mt-5 grid gap-4 sm:mt-6 lg:grid-cols-2 lg:gap-5">
      {customerData.length > 0 ? (
        <ChartPanel title="前五客户集中度（分主体）" delayMs={delayMs} height="h-auto min-h-[220px]">
          <SubjectConcentrationChart data={customerData} chartH={chartH} valueName="前五客户合计占比" />
        </ChartPanel>
      ) : null}
      {supplierData.length > 0 ? (
        <ChartPanel title="前五供应商集中度（分主体）" delayMs={delayMs + 40} height="h-auto min-h-[220px]">
          <SubjectConcentrationChart data={supplierData} chartH={chartH} valueName="前五供应商合计占比" />
        </ChartPanel>
      ) : null}
    </div>
  );
}
