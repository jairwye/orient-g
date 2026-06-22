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
import { ChapterPanel } from "../components/ChapterPanel";
import { ChartPanel } from "../components/ChartPanel";
import { CompetitorChartTooltip, competitorBarTooltipProps } from "../components/CompetitorChartTooltip";
import { DataTable } from "../components/DataTable";
import { BlueprintAnalysisPanel } from "../components/BlueprintAnalysisPanel";
import { Sec09CustomerExplorer } from "../components/Sec09CustomerExplorer";
import { Sec09CustomerViz } from "../components/Sec09CustomerViz";
import { parseCustomerCompanyTables } from "../lib/sec09_customer_blocks";
import { Sec09OperatingProductsExplorer } from "../components/Sec09OperatingProductsExplorer";
import { Sec09RelatedPartyExplorer } from "../components/Sec09RelatedPartyExplorer";
import { Sec09RndProjectExplorer } from "../components/Sec09RndProjectExplorer";
import { GovSubsidyDetailPanel } from "../components/Sec09Blueprints";
import { Sec09BlockStream } from "../components/Sec09BlockStream";
import { SubjectAnalysisBoard } from "../components/SubjectAnalysisBoard";
import { TopicSubjectBoard } from "../components/TopicSubjectBoard";
import { BUSINESS_CHART_COLORS } from "../../lib/business_chart_colors";
import { CHART_CARTESIAN_GRID, CHART_X_AXIS, CHART_Y_AXIS, colorForCompany } from "../lib/competitor_chart_colors";
import { companyColsForSnapshot, colToLabel, rowValueForCompany } from "../lib/companies";
import { CL, FK, FK_METRIC } from "../lib/field_keys";
import { formatDecimal2, formatPctPoints, parseNum, toPercentPoints } from "../lib/format";
import { subTitleForSnap } from "../lib/navigation";
import { buildSec09SubjectGroups } from "../lib/sec09_subject_analysis";
import { buildTopicSubjectGroups } from "../lib/sec09_topic_subject_analysis";
import { mergeRndProjectTable } from "../lib/sec09_table_transforms";
import { stripBlocksAfterLastTable } from "../lib/sec09_block_utils";
import { relatedPartyChangeFormatCell } from "../lib/related_party_change_format";
import { getAnchorAnalysisMarkdown, getAnchorBlocks, getGovSubsidyDetailTable, getNarrativeMarkdown, getTable, getTables } from "../lib/selectors";
import { type SectionProps } from "../lib/section_ui";

const SNAP_ANCHORS: Record<string, string> = {
  "sec-09-a": "sec-09-1",
  "sec-09-b": "sec-09-2",
  "sec-09-c": "sec-09-3",
  "sec-09-d": "sec-09-4",
  "sec-09-e": "sec-09-5",
  "sec-09-f": "sec-09-6",
  "sec-09-g": "sec-09-7",
  "sec-09-h": "sec-09-8",
  "sec-09-i": "sec-09-9",
  "sec-09-j": "sec-09-10",
  "sec-09-k": "sec-09-11",
  "sec-09-l": "sec-09-12",
  "sec-09-m": "sec-09-13",
  "sec-09-n": "sec-09-14",
  "sec-09-o": "sec-09-15",
};

/** sec-09-j~o：蓝本 block 流屏，分析叙事单独抽取 */
const SEC09_BLOCK_ANCHORS = new Set([
  "sec-09-10",
  "sec-09-11",
  "sec-09-12",
  "sec-09-13",
  "sec-09-14",
  "sec-09-15",
]);

const TOPIC_SUBJECT_ANCHORS = new Set(["sec-09-8", "sec-09-9", "sec-09-10", "sec-09-11"]);
const BLUEPRINT_ANALYSIS_ANCHORS = new Set(["sec-09-13"]);

function metricBars(
  table: ReturnType<typeof getTable>,
  metric: string,
  snapshot: SectionProps["snapshot"],
  opts?: { asPct?: boolean },
) {
  const row = table?.rows.find((r) => String(r[FK.metric] ?? "") === metric);
  if (!row) return [];
  const cols = companyColsForSnapshot(snapshot, table?.headers);
  return cols.map((col) => {
    const raw = parseNum(rowValueForCompany(row, col));
    if (raw == null) return null;
    const value = opts?.asPct ? toPercentPoints(raw) : raw;
    return { name: colToLabel(col, snapshot), value, fill: colorForCompany(col, snapshot) };
  })
    .filter(Boolean)
    .sort((a, b) => b!.value - a!.value) as Array<{ name: string; value: number; fill: string }>;
}

function AnalysisCards({
  snapshot,
  subjectGroups,
  topicSubjectGroups,
  blueprintAnalysis,
  delayMs = 120,
}: {
  snapshot: SectionProps["snapshot"];
  subjectGroups?: ReturnType<typeof buildSec09SubjectGroups>;
  topicSubjectGroups?: ReturnType<typeof buildTopicSubjectGroups>;
  blueprintAnalysis?: string;
  delayMs?: number;
}) {
  return (
    <>
      {topicSubjectGroups && topicSubjectGroups.length > 0 ? (
        <TopicSubjectBoard groups={topicSubjectGroups} snapshot={snapshot} delayMs={delayMs} />
      ) : null}
      {blueprintAnalysis ? <BlueprintAnalysisPanel markdown={blueprintAnalysis} delayMs={delayMs} /> : null}
      {subjectGroups && subjectGroups.length > 0 ? (
        <SubjectAnalysisBoard groups={subjectGroups} snapshot={snapshot} delayMs={delayMs + 20} />
      ) : null}
    </>
  );
}

function SectionSlide({
  children,
  snapshot,
  subjectGroups,
  topicSubjectGroups,
  blueprintAnalysis,
}: {
  children: ReactNode;
  snapshot: SectionProps["snapshot"];
  subjectGroups?: ReturnType<typeof buildSec09SubjectGroups>;
  topicSubjectGroups?: ReturnType<typeof buildTopicSubjectGroups>;
  blueprintAnalysis?: string;
}) {
  return (
    <div className="space-y-4 sm:space-y-5">
      {children}
      <AnalysisCards
        snapshot={snapshot}
        subjectGroups={subjectGroups}
        topicSubjectGroups={topicSubjectGroups}
        blueprintAnalysis={blueprintAnalysis}
      />
    </div>
  );
}

export function Sec09Others({ snapshot }: SectionProps) {
  const analysisByAnchor = useMemo(() => {
    const subject: Record<string, ReturnType<typeof buildSec09SubjectGroups>> = {};
    const topicSubject: Record<string, ReturnType<typeof buildTopicSubjectGroups>> = {};
    const blueprint: Record<string, string> = {};
    for (const anchor of Object.values(SNAP_ANCHORS)) {
      const md = SEC09_BLOCK_ANCHORS.has(anchor)
        ? getAnchorAnalysisMarkdown(snapshot, anchor)
        : getNarrativeMarkdown(snapshot, anchor);
      if (!md) continue;
      if (BLUEPRINT_ANALYSIS_ANCHORS.has(anchor)) {
        blueprint[anchor] = md;
      } else if (TOPIC_SUBJECT_ANCHORS.has(anchor)) {
        topicSubject[anchor] = buildTopicSubjectGroups(md, snapshot);
      } else {
        subject[anchor] = buildSec09SubjectGroups(md, snapshot);
      }
    }
    return { subject, topicSubject, blueprint };
  }, [snapshot]);

  const rent = getTable(snapshot, "sec-09-1");
  const roi = getTable(snapshot, "sec-09-2");
  const govTables = getTables(snapshot, "sec-09-3");
  const govDetailTable = getGovSubsidyDetailTable(snapshot);
  const rndProjects = getTable(snapshot, "sec-09-4");
  const dividend = getTable(snapshot, "sec-09-5");
  const currency = getTable(snapshot, "sec-09-6");
  const investment = getTable(snapshot, "sec-09-7");
  const arAging = getTable(snapshot, "sec-09-8");
  const productTables = getTables(snapshot, "sec-09-9");

  const roiData = useMemo(() => metricBars(roi, FK_METRIC.compositeRoi, snapshot), [roi, snapshot]);
  const rentData = useMemo(() => metricBars(rent, FK_METRIC.rentPerCap, snapshot), [rent, snapshot]);

  const sec09Cols = useMemo(
    () => companyColsForSnapshot(snapshot, roi?.headers ?? currency?.headers),
    [snapshot, roi?.headers, currency?.headers],
  );

  const adShareData = useMemo(() => {
    const row = roi?.rows.find((r) => String(r[FK.metric] ?? "") === FK_METRIC.adSalesRatio);
    if (!row) return [];
    return sec09Cols.map((col) => {
      const raw = parseNum(rowValueForCompany(row, col));
      if (raw == null) return null;
      const pct = toPercentPoints(raw);
      return {
        name: colToLabel(col, snapshot),
        value: pct,
        fill: colorForCompany(col, snapshot),
      };
    }).filter(Boolean).sort((a, b) => b!.value - a!.value);
  }, [roi, sec09Cols, snapshot]);

  const fxMixData = useMemo(() => {
    const rmbRow = currency?.rows.find((r) => String(r[FK.metric] ?? "").includes("人民币占比"));
    const fxRow = currency?.rows.find((r) => String(r[FK.metric] ?? "").includes("外币占比"));
    if (!rmbRow && !fxRow) return [];
    const cols = companyColsForSnapshot(snapshot, currency?.headers);
    return cols.map((col) => {
      const rmb = rmbRow ? toPercentPoints(parseNum(rowValueForCompany(rmbRow, col)) ?? 0) : 0;
      const fx = fxRow ? toPercentPoints(parseNum(rowValueForCompany(fxRow, col)) ?? 0) : 0;
      if (rmb === 0 && fx === 0) return null;
      return { name: colToLabel(col, snapshot), rmb, fx };
    }).filter(Boolean);
  }, [currency, snapshot]);

  const arOver1y = useMemo(() => {
    if (!arAging?.rows.length) return [];
    return arAging.rows
      .map((row) => {
        const co = String(row[FK.company] ?? "");
        const pct = parseNum(row["1\u5e74\u4ee5\u4e0a\u5360\u6bd4"]);
        if (pct == null) return null;
        return { name: colToLabel(co, snapshot), value: toPercentPoints(pct) };
      })
      .filter(Boolean)
      .sort((a, b) => b!.value - a!.value);
  }, [arAging?.rows, snapshot]);

  const rndMerged = useMemo(
    () => (rndProjects ? mergeRndProjectTable(rndProjects) : null),
    [rndProjects],
  );
  const chartH = Math.max(240, roiData.length * 36 + 56);
  const productsSummary = productTables[0];
  const productsDetail = productTables[1];

  const roiCharts = (
    <div className="mt-5 grid gap-5 lg:grid-cols-2 lg:gap-6">
      <ChartPanel title={CL.compositeRoi} delayMs={60} height="h-auto min-h-[240px]">
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
      <ChartPanel title={CL.adSalesShare} delayMs={80} height="h-auto min-h-[240px]">
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
    <ChartPanel title={CL.rentPerCap} delayMs={60} height="h-auto min-h-[240px]">
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
    <ChartPanel title={CL.currencyMix} delayMs={60} height="h-auto min-h-[240px]">
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
    <ChartPanel title={CL.arOver1yShare} delayMs={60} height="h-auto min-h-[220px]">
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

  const subSlide = (
    id: string,
    content: ReactNode,
    opts?: {
      dense?: boolean;
      subjectAnchor?: string;
      topicSubjectAnchor?: string;
      blueprintAnalysisAnchor?: string;
    },
  ) => ({
    id,
    title: subTitleForSnap(id),
    subOnly: true as const,
    dense: opts?.dense,
    content: (
      <SectionSlide
        snapshot={snapshot}
        subjectGroups={opts?.subjectAnchor ? analysisByAnchor.subject[opts.subjectAnchor] : undefined}
        topicSubjectGroups={
          opts?.topicSubjectAnchor ? analysisByAnchor.topicSubject[opts.topicSubjectAnchor] : undefined
        }
        blueprintAnalysis={
          opts?.blueprintAnalysisAnchor ? analysisByAnchor.blueprint[opts.blueprintAnalysisAnchor] : undefined
        }
      >
        {content}
      </SectionSlide>
    ),
  });

  const blockSlide = (
    snapId: string,
    defaultTitle: string,
    opts?: { topicSubject?: boolean; hideLicenseColumn?: boolean },
  ) => {
    const anchor = SNAP_ANCHORS[snapId]!;
    const blocks = getAnchorBlocks(snapshot, anchor);
    const analysisMd = getAnchorAnalysisMarkdown(snapshot, anchor);
    const useBlueprint = BLUEPRINT_ANALYSIS_ANCHORS.has(anchor);
    return subSlide(
      snapId,
      blocks.length > 0 ? (
        <Sec09BlockStream
          blocks={blocks}
          defaultTableTitle={defaultTitle}
          wrapText
          hideLicenseColumn={opts?.hideLicenseColumn}
        />
      ) : (
        <p className="text-sm text-zinc-500">蓝本 {anchor} 暂无表格数据，请保存 MD 并在财务后台重新上传解析。</p>
      ),
      {
        dense: true,
        subjectAnchor: analysisMd && !opts?.topicSubject && !useBlueprint ? anchor : undefined,
        topicSubjectAnchor: analysisMd && opts?.topicSubject ? anchor : undefined,
        blueprintAnalysisAnchor: useBlueprint && analysisMd ? anchor : undefined,
      },
    );
  };

  return (
    <ChapterPanel
      sectionId="sec-09"
      slides={[
        {
          id: "sec-09-a",
          title: subTitleForSnap("sec-09-a"),
          dense: true,
          content: (
            <SectionSlide snapshot={snapshot} subjectGroups={analysisByAnchor.subject["sec-09-1"]}>
              {rent ? <DataTable title={CL.rentOffice} headers={rent.headers} rows={rent.rows} delayMs={40} compact /> : null}
              {rentChart}
            </SectionSlide>
          ),
        },
        subSlide(
          "sec-09-b",
          <>
            {roi ? <DataTable title={CL.roiAds} headers={roi.headers} rows={roi.rows} delayMs={40} compact /> : null}
            {roiCharts}
          </>,
          { dense: true, subjectAnchor: "sec-09-2" },
        ),
        subSlide(
          "sec-09-c",
          <>
            {govTables[0] ? (
              <DataTable title={CL.govSubsidy} headers={govTables[0].headers} rows={govTables[0].rows} delayMs={40} compact />
            ) : null}
            <div className="mt-5 sm:mt-6">
              <GovSubsidyDetailPanel table={govDetailTable} snapshot={snapshot} delayMs={60} />
            </div>
          </>,
          { dense: true, subjectAnchor: "sec-09-3" },
        ),
        subSlide(
          "sec-09-d",
          rndMerged ? <Sec09RndProjectExplorer table={rndMerged} /> : null,
          { dense: true, subjectAnchor: "sec-09-4" },
        ),
        subSlide(
          "sec-09-e",
          dividend ? (
            <DataTable
              title={CL.shareholderDiv}
              headers={dividend.headers}
              rows={dividend.rows}
              delayMs={40}
              compact
              wrapText
            />
          ) : null,
          { dense: true },
        ),
        subSlide(
          "sec-09-f",
          <>
            {currency ? <DataTable title={CL.currencyMix} headers={currency.headers} rows={currency.rows} delayMs={40} compact /> : null}
            {fxChart}
          </>,
          { dense: true, subjectAnchor: "sec-09-6" },
        ),
        subSlide(
          "sec-09-g",
          investment ? (
            <DataTable title={CL.investmentAlloc} headers={investment.headers} rows={investment.rows} delayMs={40} compact />
          ) : null,
          { dense: true, subjectAnchor: "sec-09-7" },
        ),
        subSlide(
          "sec-09-h",
          <>
            {arAging ? <DataTable title={CL.arAgingStruct} headers={arAging.headers} rows={arAging.rows} delayMs={40} compact /> : null}
            {arChart}
          </>,
          { dense: true, topicSubjectAnchor: "sec-09-8" },
        ),
        subSlide(
          "sec-09-i",
          productsSummary && productsDetail ? (
            <Sec09OperatingProductsExplorer
              summary={productsSummary}
              detail={productsDetail}
              snapshot={snapshot}
            />
          ) : null,
          { dense: true, topicSubjectAnchor: "sec-09-9" },
        ),
        blockSlide("sec-09-j", CL.majorGames, { topicSubject: true, hideLicenseColumn: true }),
        blockSlide("sec-09-k", CL.gameMetrics, { topicSubject: true }),
        subSlide(
          "sec-09-l",
          (() => {
            const rp = getTable(snapshot, "sec-09-12");
            const note = getNarrativeMarkdown(snapshot, "sec-09-12");
            return (
              <>
                {note ? <p className="text-xs leading-relaxed text-zinc-500">{note.replace(/^\*|\*$/g, "")}</p> : null}
                {rp ? <Sec09RelatedPartyExplorer table={rp} /> : null}
              </>
            );
          })(),
          { dense: true, subjectAnchor: "sec-09-12" },
        ),
        subSlide(
          "sec-09-m",
          (() => {
            const blocks = getAnchorBlocks(snapshot, "sec-09-13");
            const companyTables = parseCustomerCompanyTables(blocks);
            return blocks.length > 0 ? (
              <>
                <Sec09CustomerExplorer blocks={blocks} snapshot={snapshot} />
                <Sec09CustomerViz companyTables={companyTables} snapshot={snapshot} delayMs={60} />
              </>
            ) : (
              <p className="text-sm text-zinc-500">蓝本 sec-09-13 暂无表格数据。</p>
            );
          })(),
          { dense: true, blueprintAnalysisAnchor: "sec-09-13" },
        ),
        blockSlide("sec-09-n", CL.consolidationScopeChange),
        subSlide(
          "sec-09-o",
          (() => {
            const blocks = stripBlocksAfterLastTable(getAnchorBlocks(snapshot, "sec-09-15"));
            return blocks.length > 0 ? (
              <Sec09BlockStream
                blocks={blocks}
                defaultTableTitle={CL.relatedPartyChange}
                wrapText
                formatCell={relatedPartyChangeFormatCell}
                endDivider
              />
            ) : (
              <p className="text-sm text-zinc-500">蓝本 sec-09-15 暂无表格数据，请保存 MD 并在财务后台重新上传解析。</p>
            );
          })(),
          { dense: true },
        ),
      ]}
    />
  );
}
