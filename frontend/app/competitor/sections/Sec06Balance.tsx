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
import { ChapterPanel } from "../components/ChapterPanel";
import { ChartPanel } from "../components/ChartPanel";
import {
  CompetitorChartTooltip,
  competitorBarTooltipProps,
  competitorScatterTooltipProps,
} from "../components/CompetitorChartTooltip";
import { DataTable } from "../components/DataTable";
import { SubjectAnalysisBoard } from "../components/SubjectAnalysisBoard";
import { TopicAnalysisBoard } from "../components/TopicAnalysisBoard";
import { BUSINESS_CHART_COLORS } from "../../lib/business_chart_colors";
import {
  CHART_CARTESIAN_GRID,
  CHART_X_AXIS,
  CHART_Y_AXIS,
  colorForCompany,
} from "../lib/competitor_chart_colors";
import { buildSubjectAnalysisGroups } from "../lib/balance_subject_analysis";
import { buildTopicAnalysisGroups } from "../lib/topic_analysis";
import { COMPANY_COLS, colToLabel } from "../lib/companies";
import {
  deriveAssetFpaInsights,
  deriveBalanceInsights,
  deriveChangeFpaInsights,
  deriveLiquidityFpaInsights,
  impliedDupontRoe,
  parseDupontPoints,
  peerMedian,
} from "../lib/finance_analysis";
import { CL, FK, FK_CHANGE, FK_METRIC } from "../lib/field_keys";
import {
  formatDecimal2,
  formatPctPoints,
  formatSolvencyMetricValue,
  formatTableCell,
  parseNum,
  toPercentPoints,
} from "../lib/format";
import { subTitleForSnap } from "../lib/navigation";
import { getTable } from "../lib/selectors";
import { type SectionProps } from "../lib/section_ui";

/** 变动 diverging 图（不含应付职工薪酬） */
const CHANGE_CHART_SUBJECTS = [
  "\u8d27\u5e01\u8d44\u91d1",
  "\u5e94\u6536\u8d26\u6b3e",
  "\u77ed\u671f\u501f\u6b3e",
] as const;

function formatDeltaWan(v: number): string {
  const sign = v > 0 ? "+" : "";
  return `${sign}${Math.round(v).toLocaleString("zh-CN")} \u4e07`;
}

function metricRowValue(
  table: ReturnType<typeof getTable>,
  metric: string,
  col: string,
): number | null {
  const row = table?.rows.find((r) => String(r[FK.metric] ?? "") === metric);
  if (!row) return null;
  return parseNum(row[col]);
}

function changeRowValue(
  table: ReturnType<typeof getTable>,
  subject: string,
  col: string,
): number | null {
  const row = table?.rows.find((r) => String(r[FK_CHANGE] ?? r[FK.subject] ?? "") === subject);
  if (!row) return null;
  return parseNum(row[col]);
}

function assetRowValue(
  table: ReturnType<typeof getTable>,
  subjectPrefix: string,
  col: string,
): number | null {
  const row = table?.rows.find((r) => String(r[FK.subject] ?? "").startsWith(subjectPrefix));
  if (!row) return null;
  return parseNum(row[col]);
}

function buildMetricBars(
  table: ReturnType<typeof getTable>,
  metric: string,
  snapshot: SectionProps["snapshot"],
  sortDesc = true,
) {
  const rows = COMPANY_COLS.map((col) => {
    const v = metricRowValue(table, metric, col);
    if (v == null) return null;
    return {
      name: colToLabel(col),
      colKey: col,
      value: v,
      fill: colorForCompany(col, snapshot),
    };
  }).filter(Boolean) as Array<{ name: string; colKey: string; value: number; fill: string }>;
  return sortDesc ? rows.sort((a, b) => b.value - a.value) : rows;
}

function buildChangeBars(table: ReturnType<typeof getTable>, subject: string) {
  return COMPANY_COLS.map((col) => {
    const delta = changeRowValue(table, subject, col);
    if (delta == null) return null;
    return {
      name: colToLabel(col),
      colKey: col,
      delta,
      fill: delta >= 0 ? BUSINESS_CHART_COLORS.actual : "#ef4444",
    };
  })
    .filter(Boolean)
    .sort((a, b) => b!.delta - a!.delta) as Array<{
    name: string;
    colKey: string;
    delta: number;
    fill: string;
  }>;
}

function DivergingChangeChart({
  title,
  data,
  delayMs,
}: {
  title: string;
  data: ReturnType<typeof buildChangeBars>;
  delayMs: number;
}) {
  if (!data.length) return null;
  const h = Math.max(200, data.length * 32 + 48);
  return (
    <ChartPanel title={title} delayMs={delayMs} height="h-auto min-h-[200px]">
      <div style={{ height: h }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} layout="vertical" margin={{ left: 4, right: 12, top: 4, bottom: 4 }}>
            <CartesianGrid {...CHART_CARTESIAN_GRID} horizontal={false} />
            <XAxis
              type="number"
              {...CHART_X_AXIS}
              tickFormatter={(v) => `${Number(v) > 0 ? "+" : ""}${Math.round(Number(v) / 10000)}`}
              tick={{ fontSize: 9 }}
            />
            <YAxis
              type="category"
              dataKey="name"
              {...CHART_Y_AXIS}
              width={72}
              interval={0}
              tick={{ fontSize: 9 }}
            />
            <ReferenceLine x={0} stroke="#52525b" />
            <Tooltip
              {...competitorBarTooltipProps({
                content: <CompetitorChartTooltip valueFormatter={(v) => formatDeltaWan(Number(v))} />,
              })}
            />
            <Bar dataKey="delta" name={title} radius={[0, 3, 3, 0]}>
              {data.map((d, i) => (
                <Cell key={i} fill={d.fill} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </ChartPanel>
  );
}

function narrativeMarkdown(blocks: SectionProps["snapshot"]["sections"][0]["blocks"], anchor: string): string {
  const hit = blocks.find((b) => b.kind === "narrative" && b.anchor === anchor);
  if (!hit || hit.kind !== "narrative") return "";
  return hit.markdown?.trim() ?? "";
}

export function Sec06Balance({ snapshot }: SectionProps) {
  const blocks = useMemo(() => snapshot.sections.find((s) => s.id === "sec-06")?.blocks ?? [], [snapshot]);
  const assets = getTable(snapshot, "sec-06-1");
  const changes = getTable(snapshot, "sec-06-2");
  const solvency = getTable(snapshot, "sec-06-3");
  const dupont = getTable(snapshot, "sec-06-4");

  const assetInsights = useMemo(() => deriveAssetFpaInsights(snapshot), [snapshot]);
  const changeInsights = useMemo(() => deriveChangeFpaInsights(snapshot), [snapshot]);
  const liquidityInsights = useMemo(() => deriveLiquidityFpaInsights(snapshot), [snapshot]);
  const dupontInsights = useMemo(() => deriveBalanceInsights(snapshot), [snapshot]);
  const dupontPoints = useMemo(() => parseDupontPoints(snapshot), [snapshot]);

  const balanceInsights = useMemo(
    () => [...assetInsights, ...changeInsights],
    [assetInsights, changeInsights],
  );

  const balanceAnalysisMarkdown = useMemo(() => narrativeMarkdown(blocks, "sec-06-2"), [blocks]);

  const subjectAnalysisGroups = useMemo(
    () => buildSubjectAnalysisGroups(balanceAnalysisMarkdown, balanceInsights),
    [balanceAnalysisMarkdown, balanceInsights],
  );

  const dupontAnalysisMarkdown = useMemo(() => narrativeMarkdown(blocks, "sec-06-4"), [blocks]);

  const dupontTopicInsights = useMemo(
    () => [...dupontInsights, ...liquidityInsights],
    [dupontInsights, liquidityInsights],
  );

  const topicAnalysisGroups = useMemo(
    () => buildTopicAnalysisGroups(dupontAnalysisMarkdown, dupontTopicInsights),
    [dupontAnalysisMarkdown, dupontTopicInsights],
  );

  const cashDebtData = useMemo(
    () =>
      COMPANY_COLS.map((col) => {
        const cash = assetRowValue(assets, "\u8d27\u5e01\u8d44\u91d1", col);
        const debt = assetRowValue(assets, "\u77ed\u671f\u501f\u6b3e", col);
        if (cash == null && debt == null) return null;
        return {
          name: colToLabel(col),
          cash: (cash ?? 0) / 10000,
          debt: (debt ?? 0) / 10000,
        };
      })
        .filter(Boolean)
        .sort((a, b) => b!.cash - a!.cash),
    [assets],
  );

  const changeCharts = useMemo(
    () =>
      CHANGE_CHART_SUBJECTS.map((subject) => ({
        subject,
        data: buildChangeBars(changes, subject),
      })),
    [changes],
  );

  const netCashData = useMemo(
    () => buildMetricBars(solvency, FK_METRIC.netCash, snapshot),
    [solvency, snapshot],
  );
  const currentRatioData = useMemo(
    () => buildMetricBars(solvency, FK_METRIC.currentRatio, snapshot),
    [solvency, snapshot],
  );
  const liquidityCompareData = useMemo(
    () =>
      COMPANY_COLS.map((col) => {
        const current = metricRowValue(solvency, FK_METRIC.currentRatio, col);
        const quick = metricRowValue(solvency, FK_METRIC.quickRatio, col);
        if (current == null && quick == null) return null;
        return {
          name: colToLabel(col),
          current: current ?? 0,
          quick: quick ?? 0,
        };
      })
        .filter(Boolean)
        .sort((a, b) => b!.current - a!.current),
    [solvency],
  );

  const turnoverData = useMemo(
    () => buildMetricBars(solvency, FK_METRIC.assetTurnover, snapshot),
    [solvency, snapshot],
  );
  const arShareData = useMemo(
    () =>
      COMPANY_COLS.map((col) => {
        const raw = metricRowValue(solvency, FK_METRIC.arToCurrent, col);
        if (raw == null) return null;
        return {
          name: colToLabel(col),
          value: toPercentPoints(raw),
          fill: colorForCompany(col, snapshot),
        };
      })
        .filter(Boolean)
        .sort((a, b) => b!.value - a!.value),
    [solvency, snapshot],
  );

  const roeData = useMemo(
    () =>
      dupontPoints
        .map((d) => ({
          name: d.name,
          roe: d.roe,
          netMargin: d.netMargin,
          turnover: d.turnover,
          leverage: d.leverage,
          driverLabel: d.driverLabel,
          fill: colorForCompany(d.colKey, snapshot),
        }))
        .sort((a, b) => b.roe - a.roe),
    [dupontPoints, snapshot],
  );

  const scatterData = useMemo(
    () =>
      dupontPoints.map((d) => ({
        ...d,
        fill: colorForCompany(d.colKey, snapshot),
        z: Math.max(80, Math.min(420, d.leverage * 120)),
      })),
    [dupontPoints, snapshot],
  );

  const dupontRowsWithImplied = useMemo(() => {
    if (!dupont?.rows.length) return { headers: [] as string[], rows: [] as Record<string, string | number | null>[] };
    const headers = [...dupont.headers, CL.impliedRoe];
    const rows = dupont.rows.map((row) => {
      const margin = toPercentPoints(parseNum(row["\u51c0\u5229\u7387"]) ?? 0);
      const turn = parseNum(row["\u603b\u8d44\u4ea7\u5468\u8f6c\u7387"]) ?? 0;
      const lev = parseNum(row["\u6743\u76ca\u4e58\u6570"]) ?? 0;
      const implied = impliedDupontRoe(margin, turn, lev);
      return { ...row, [CL.impliedRoe]: implied / 100 };
    });
    return { headers, rows };
  }, [dupont]);

  const medMargin = peerMedian(dupontPoints.map((d) => d.netMargin));
  const medTurn = peerMedian(dupontPoints.map((d) => d.turnover));
  const roeMedian = peerMedian(roeData.map((d) => d.roe));
  const ratioMedian = peerMedian(currentRatioData.map((d) => d.value));
  const barH = (n: number) => Math.max(220, n * 34 + 52);
  const roeChartHeight = Math.max(280, roeData.length * 40 + 64);
  const cashDebtH = Math.max(240, cashDebtData.length * 36 + 56);

  return (
    <ChapterPanel
      sectionId="sec-06"
      slides={[
        {
          id: "sec-06-a",
          title: subTitleForSnap("sec-06-a"),
          content: (
            <>
              {assets ? (
                <DataTable
                  title={CL.balanceSheetItems}
                  headers={assets.headers}
                  rows={assets.rows}
                  delayMs={40}
                  compact
                />
              ) : null}
              {changes ? (
                <div className="mt-4 sm:mt-5">
                  <DataTable
                    title={CL.balanceSheetChanges}
                    headers={changes.headers}
                    rows={changes.rows}
                    delayMs={60}
                    compact
                  />
                </div>
              ) : null}
              <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:gap-5">
                <ChartPanel title={CL.cashVsStDebt} delayMs={80} height="h-auto min-h-[240px]">
                  <div style={{ height: cashDebtH }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart
                        data={cashDebtData}
                        layout="vertical"
                        margin={{ left: 4, right: 16, top: 4, bottom: 4 }}
                      >
                        <CartesianGrid {...CHART_CARTESIAN_GRID} horizontal={false} />
                        <XAxis type="number" {...CHART_X_AXIS} unit={CL.unitYi} tick={{ fontSize: 10 }} />
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
                            content: (
                              <CompetitorChartTooltip valueFormatter={(v) => `${formatDecimal2(v)} ${CL.unitYi}`} />
                            ),
                          })}
                        />
                        <Legend wrapperStyle={{ fontSize: 10 }} />
                        <Bar dataKey="cash" name={CL.cashOnHand} fill={BUSINESS_CHART_COLORS.actual} radius={[0, 3, 3, 0]} />
                        <Bar dataKey="debt" name={CL.shortTermDebt} fill="#d97706" radius={[0, 3, 3, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                  <p className="mt-2 text-xs text-zinc-500">期末毛现金 vs 短借，差值即净现金的第一层近似。</p>
                </ChartPanel>
                {changeCharts.map(({ subject, data }, idx) => (
                  <DivergingChangeChart
                    key={subject}
                    title={`\u53d8\u52a8 \u00b7 ${subject}(\u4e07)`}
                    data={data}
                    delayMs={100 + idx * 40}
                  />
                ))}
              </div>
              <SubjectAnalysisBoard groups={subjectAnalysisGroups} snapshot={snapshot} delayMs={200} />
            </>
          ),
        },
        {
          id: "sec-06-b",
          title: subTitleForSnap("sec-06-b"),
          content: (
            <>
              {solvency ? (
                <DataTable
                  title={CL.solvencyMetricsTable}
                  headers={solvency.headers}
                  rows={solvency.rows}
                  delayMs={40}
                  compact
                  formatCell={(h, v, row) => {
                    if (h === FK.metric) return formatTableCell(h, v);
                    const metric = String(row?.[FK.metric] ?? "");
                    return formatSolvencyMetricValue(metric, v);
                  }}
                />
              ) : null}
              <div className="mt-5 grid gap-5 lg:grid-cols-2 lg:gap-6">
                <ChartPanel title={CL.netCash} delayMs={60} height="h-auto min-h-[220px]">
                  <div style={{ height: barH(netCashData.length) }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={netCashData} layout="vertical" margin={{ left: 4, right: 16, top: 4, bottom: 4 }}>
                        <CartesianGrid {...CHART_CARTESIAN_GRID} horizontal={false} />
                        <XAxis type="number" {...CHART_X_AXIS} unit={CL.unitYi} tick={{ fontSize: 10 }} />
                        <YAxis type="category" dataKey="name" {...CHART_Y_AXIS} width={80} interval={0} tick={{ fontSize: 10 }} />
                        <Tooltip
                          {...competitorBarTooltipProps({
                            content: <CompetitorChartTooltip valueFormatter={(v) => `${formatDecimal2(v)} \u4ebf`} />,
                          })}
                        />
                        <Bar dataKey="value" name={CL.netCash} radius={[0, 3, 3, 0]}>
                          {netCashData.map((d, i) => (
                            <Cell key={i} fill={d.fill} />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </ChartPanel>
                <ChartPanel title={`${CL.currentRatio} / ${CL.quickRatio}`} delayMs={80} height="h-auto min-h-[220px]">
                  <div style={{ height: barH(liquidityCompareData.length) }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={liquidityCompareData} layout="vertical" margin={{ left: 4, right: 16, top: 4, bottom: 4 }}>
                        <CartesianGrid {...CHART_CARTESIAN_GRID} horizontal={false} />
                        <XAxis type="number" domain={[0, "auto"]} {...CHART_X_AXIS} tick={{ fontSize: 10 }} />
                        <YAxis type="category" dataKey="name" {...CHART_Y_AXIS} width={80} interval={0} tick={{ fontSize: 10 }} />
                        <ReferenceLine x={1} stroke="#22c55e" strokeDasharray="4 4" />
                        {ratioMedian != null && (
                          <ReferenceLine x={ratioMedian} stroke="#2563eb" strokeDasharray="4 4" />
                        )}
                        <Tooltip {...competitorBarTooltipProps({ content: <CompetitorChartTooltip valueFormatter={(v) => formatDecimal2(v)} /> })} />
                        <Legend wrapperStyle={{ fontSize: 10 }} />
                        <Bar dataKey="current" name={CL.currentRatio} fill={BUSINESS_CHART_COLORS.current} radius={[0, 3, 3, 0]} />
                        <Bar dataKey="quick" name={CL.quickRatio} fill={BUSINESS_CHART_COLORS.actual} radius={[0, 3, 3, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                  <p className="mt-2 text-xs text-zinc-500">绿线=1.0；流动 vs 速动差距反映预付/存货占用。</p>
                </ChartPanel>
                <ChartPanel title={CL.assetTurnover} delayMs={100} height="h-auto min-h-[220px]">
                  <div style={{ height: barH(turnoverData.length) }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={turnoverData} layout="vertical" margin={{ left: 4, right: 16, top: 4, bottom: 4 }}>
                        <CartesianGrid {...CHART_CARTESIAN_GRID} horizontal={false} />
                        <XAxis type="number" {...CHART_X_AXIS} tick={{ fontSize: 10 }} />
                        <YAxis type="category" dataKey="name" {...CHART_Y_AXIS} width={80} interval={0} tick={{ fontSize: 10 }} />
                        <Tooltip
                          {...competitorBarTooltipProps({
                            content: <CompetitorChartTooltip valueFormatter={(v) => `${formatDecimal2(v)}x`} />,
                          })}
                        />
                        <Bar dataKey="value" name={CL.assetTurnover} radius={[0, 3, 3, 0]}>
                          {turnoverData.map((d, i) => (
                            <Cell key={i} fill={d.fill} />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </ChartPanel>
                <ChartPanel title={CL.arToCurrentAssets} delayMs={120} height="h-auto min-h-[220px]">
                  <div style={{ height: barH(arShareData.length) }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={arShareData} layout="vertical" margin={{ left: 4, right: 16, top: 4, bottom: 4 }}>
                        <CartesianGrid {...CHART_CARTESIAN_GRID} horizontal={false} />
                        <XAxis type="number" {...CHART_X_AXIS} unit="%" tick={{ fontSize: 10 }} />
                        <YAxis type="category" dataKey="name" {...CHART_Y_AXIS} width={80} interval={0} tick={{ fontSize: 10 }} />
                        <ReferenceLine x={10} stroke="#d97706" strokeDasharray="4 4" />
                        <Tooltip
                          {...competitorBarTooltipProps({
                            content: <CompetitorChartTooltip valueFormatter={(v) => formatPctPoints(v)} />,
                          })}
                        />
                        <Bar dataKey="value" name={CL.arToCurrentAssets} radius={[0, 3, 3, 0]}>
                          {arShareData.map((d, i) => (
                            <Cell key={i} fill={d!.value >= 12 ? "#d97706" : d!.fill} />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                  <p className="mt-2 text-xs text-zinc-500">橙线=10% 关注线；蓝本塔人 13.4% 需结合账龄判断。</p>
                </ChartPanel>
              </div>
              {dupont ? (
                <div className="mt-5 sm:mt-6">
                  <DataTable
                    title={CL.dupontTable}
                    headers={dupontRowsWithImplied.headers}
                    rows={dupontRowsWithImplied.rows}
                    delayMs={140}
                    compact
                    formatCell={(h, v) => {
                      if (h === FK.company) return formatTableCell(h, v);
                      if (h === "ROE" || h === "\u51c0\u5229\u7387" || h === CL.impliedRoe)
                        return formatPctPoints(toPercentPoints(parseNum(v) ?? 0));
                      if (String(h).includes("\u5468\u8f6c") || h === "\u6743\u76ca\u4e58\u6570")
                        return v != null ? `${formatDecimal2(parseNum(v))}x` : "\u2014";
                      return formatTableCell(h, v);
                    }}
                  />
                </div>
              ) : null}
              <div className="mt-5 grid min-h-0 flex-1 gap-5 lg:grid-cols-2 lg:gap-6">
                <ChartPanel title={CL.dupontQuadrant} delayMs={160} height="h-auto min-h-[300px]">
                  <div style={{ height: 300 }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <ScatterChart margin={{ top: 8, right: 16, bottom: 24, left: 8 }}>
                        <CartesianGrid {...CHART_CARTESIAN_GRID} />
                        <XAxis type="number" dataKey="netMargin" name={CL.netMarginRate} unit="%" {...CHART_X_AXIS} tick={{ fontSize: 10 }} />
                        <YAxis type="number" dataKey="turnover" name={CL.turnoverRate} {...CHART_Y_AXIS} tick={{ fontSize: 10 }} width={36} />
                        <ZAxis type="number" dataKey="z" range={[60, 380]} />
                        {medMargin != null && <ReferenceLine x={medMargin} stroke="#52525b" strokeDasharray="4 4" />}
                        {medTurn != null && <ReferenceLine y={medTurn} stroke="#52525b" strokeDasharray="4 4" />}
                        <Tooltip {...competitorScatterTooltipProps({ content: <CompetitorChartTooltip /> })} />
                        <Scatter data={scatterData} name="ROE">
                          {scatterData.map((d, i) => (
                            <Cell key={i} fill={d.fill} />
                          ))}
                        </Scatter>
                      </ScatterChart>
                    </ResponsiveContainer>
                  </div>
                  <p className="mt-2 text-xs text-zinc-500">{CL.dupontBubbleHint}</p>
                </ChartPanel>
                <ChartPanel title={CL.dupontRoe} delayMs={180} height="h-auto min-h-[280px]">
                  <div style={{ height: roeChartHeight }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={roeData} layout="vertical" margin={{ left: 4, right: 16, top: 4, bottom: 4 }}>
                        <CartesianGrid {...CHART_CARTESIAN_GRID} horizontal={false} />
                        <XAxis type="number" {...CHART_X_AXIS} unit="%" tick={{ fontSize: 10 }} />
                        <YAxis type="category" dataKey="name" {...CHART_Y_AXIS} width={80} interval={0} tick={{ fontSize: 10 }} />
                        {roeMedian != null && (
                          <ReferenceLine x={roeMedian} stroke="#2563eb" strokeDasharray="4 4" label={{ value: CL.medianLabel, fill: "#71717a", fontSize: 10 }} />
                        )}
                        <ReferenceLine x={0} stroke="#52525b" />
                        <Tooltip
                          {...competitorBarTooltipProps({
                            content: <CompetitorChartTooltip valueFormatter={(v) => formatPctPoints(v)} />,
                          })}
                        />
                        <Bar dataKey="roe" name="ROE" radius={[0, 3, 3, 0]}>
                          {roeData.map((d, i) => (
                            <Cell key={i} fill={d.roe >= 0 ? d.fill : "#ef4444"} />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </ChartPanel>
              </div>
              <TopicAnalysisBoard groups={topicAnalysisGroups} delayMs={200} />
            </>
          ),
        },
      ]}
    />
  );
}
