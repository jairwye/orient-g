"use client";

import { Fragment, useMemo, type ReactNode } from "react";
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
import { BUSINESS_CHART_COLORS } from "../../lib/business_chart_colors";
import { CHART_CARTESIAN_GRID, CHART_X_AXIS, CHART_Y_AXIS, colorForCompany } from "../lib/competitor_chart_colors";
import { colToLabel, companyColsForSnapshot, COMPANY_COLS, labelToCol } from "../lib/companies";
import { CL } from "../lib/field_keys";
import { formatDecimal2, parseNum } from "../lib/format";
import type { CompetitorReportSnapshot, TableBlock } from "../lib/types";
import { CompetitorChartTooltip, competitorBarTooltipProps } from "./CompetitorChartTooltip";
import { DataTable } from "./DataTable";
import { FadeInView } from "./FadeInView";

const STAGE_COLORS = {
  dev: BUSINESS_CHART_COLORS.current,
  test: "#d97706",
  live: BUSINESS_CHART_COLORS.actual,
  stop: "#71717a",
} as const;

function BlueprintShell({
  title,
  subtitle,
  children,
  delayMs = 0,
  ready = false,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  delayMs?: number;
  /** 已有蓝本数据时为 true，去掉占位样式 */
  ready?: boolean;
}) {
  return (
    <FadeInView delayMs={delayMs}>
      <div
        className={
          "rounded-lg border p-4 sm:p-5 " +
          (ready ? "border-zinc-800/80 bg-zinc-900/45" : "border-dashed border-zinc-700/80 bg-zinc-950/30")
        }
      >
        <div className="mb-4 flex flex-wrap items-start justify-between gap-2">
          <div>
            <p className="text-[10px] font-medium uppercase tracking-[0.14em] text-blue-400/80">
              {ready ? "补助明细" : "可视化方案 · 待数据"}
            </p>
            <h4 className="mt-1 text-sm font-medium text-zinc-200">{title}</h4>
            {subtitle ? <p className="mt-1 max-w-2xl text-xs leading-relaxed text-zinc-500">{subtitle}</p> : null}
          </div>
          {!ready ? (
            <span className="rounded border border-zinc-700/70 bg-zinc-900/60 px-2 py-0.5 text-[10px] text-zinc-500">占位</span>
          ) : null}
        </div>
        {children}
      </div>
    </FadeInView>
  );
}

/** 政府补助明细占位 */
export function GovSubsidyDetailPlaceholder({ delayMs = 80 }: { delayMs?: number }) {
  const columns = ["补助类型", "金额(万)", "来源/政策", "会计科目", "备注"];
  return (
    <BlueprintShell
      title={CL.govSubsidyDetail}
      subtitle="补充各公司政府补助明细表后，在此展示分项构成与同比变动。"
      delayMs={delayMs}
    >
      <div className="overflow-hidden rounded-md border border-zinc-800/80 bg-zinc-900/40">
        <div className="grid grid-cols-5 border-b border-zinc-800/80 bg-zinc-950/50 text-[11px] text-zinc-500">
          {columns.map((c) => (
            <div key={c} className="px-3 py-2 font-medium">
              {c}
            </div>
          ))}
        </div>
        {[0, 1, 2].map((i) => (
          <div key={i} className="grid grid-cols-5 border-b border-zinc-800/40 last:border-0">
            {columns.map((c) => (
              <div key={c} className="px-3 py-2.5">
                <div className="h-3 w-3/4 animate-pulse rounded bg-zinc-800/70" />
              </div>
            ))}
          </div>
        ))}
      </div>
      <p className="mt-3 text-[11px] text-zinc-600">数据就绪后可切换为明细表 + 分项堆叠柱（按公司对比补助结构）。</p>
    </BlueprintShell>
  );
}

const GOV_CO_KEY = "公司";
const GOV_AMT_KEY = "金额(万)";

function fillDownGovRows(rows: Record<string, string | number | null>[]): Record<string, string | number | null>[] {
  let last = "";
  return rows.map((row) => {
    const raw = String(row[GOV_CO_KEY] ?? "").trim();
    if (raw && raw !== "—" && raw !== "-") last = raw;
    return { ...row, [GOV_CO_KEY]: last || raw };
  });
}

function buildGovSubsidyTotals(rows: Record<string, string | number | null>[]) {
  const totals = new Map<string, number>();
  for (const row of fillDownGovRows(rows)) {
    const co = String(row[GOV_CO_KEY] ?? "").trim();
    const amt = parseNum(row[GOV_AMT_KEY]);
    if (!co || amt == null) continue;
    totals.set(co, (totals.get(co) ?? 0) + amt);
  }
  return [...totals.entries()]
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value);
}

/** 政府补助明细：有蓝本表时展示明细 + 合计柱图，否则占位 */
export function GovSubsidyDetailPanel({
  table,
  snapshot,
  delayMs = 60,
}: {
  table?: TableBlock;
  snapshot: CompetitorReportSnapshot;
  delayMs?: number;
}) {
  const displayRows = useMemo(
    () => (table?.rows.length ? fillDownGovRows(table.rows) : []),
    [table?.rows],
  );
  const chartData = useMemo(() => {
    if (!displayRows.length) return [];
    return buildGovSubsidyTotals(displayRows).map((d) => ({
      ...d,
      label: colToLabel(labelToCol(d.name) ?? d.name) || d.name,
      fill: colorForCompany(labelToCol(d.name) ?? d.name, snapshot),
    }));
  }, [displayRows, snapshot]);

  if (!table?.rows.length) {
    return <GovSubsidyDetailPlaceholder delayMs={delayMs} />;
  }

  const chartH = Math.max(180, chartData.length * 32 + 48);

  return (
    <FadeInView delayMs={delayMs}>
      <div className="mt-5 space-y-4 sm:mt-6">
        <DataTable headers={table.headers} rows={displayRows} compact wrapText delayMs={0} />
        {chartData.length > 0 ? (
          <div className="rounded-lg border border-zinc-800/80 bg-zinc-900/45 p-3 sm:p-4">
            <p className="mb-2 text-xs font-medium text-zinc-400">{CL.govSubsidyDetailTotal}</p>
          <div style={{ height: chartH }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} layout="vertical" margin={{ left: 4, right: 16, top: 4, bottom: 4 }}>
                <CartesianGrid {...CHART_CARTESIAN_GRID} horizontal={false} />
                <XAxis type="number" {...CHART_X_AXIS} tick={{ fontSize: 10 }} />
                <YAxis
                  type="category"
                  dataKey="label"
                  {...CHART_Y_AXIS}
                  width={80}
                  interval={0}
                  tick={{ fontSize: 10 }}
                />
                <Tooltip
                  {...competitorBarTooltipProps({
                    content: <CompetitorChartTooltip valueFormatter={(v) => `${formatDecimal2(v)} 万`} />,
                  })}
                />
                <Bar dataKey="value" name={CL.govSubsidyDetailTotal} radius={[0, 3, 3, 0]}>
                  {chartData.map((d, i) => (
                    <Cell key={i} fill={d.fill} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          </div>
        ) : null}
      </div>
    </FadeInView>
  );
}

/** 在研项目全景可视化方案 */
export function RndPipelineBlueprint({
  delayMs = 80,
  snapshot,
}: {
  delayMs?: number;
  snapshot?: CompetitorReportSnapshot;
}) {
  const companyCols = snapshot ? companyColsForSnapshot(snapshot) : [...COMPANY_COLS];
  const stages = [
    { key: "dev", label: "研发中", color: STAGE_COLORS.dev },
    { key: "test", label: "测试中", color: STAGE_COLORS.test },
    { key: "live", label: "已上线", color: STAGE_COLORS.live },
    { key: "stop", label: "已终止", color: STAGE_COLORS.stop },
  ] as const;

  return (
    <BlueprintShell
      title="在研项目全景"
      subtitle="按公司筛选 + 阶段泳道展示全部在研/测试/上线项目；支持项目类型标签、累计投入与备注展开。"
      delayMs={delayMs}
    >
      <div className="mb-4 flex flex-wrap gap-1.5">
        {companyCols.map((col) => (
          <span
            key={col}
            className="rounded-full border border-zinc-700/60 bg-zinc-900/50 px-2.5 py-0.5 text-[10px] text-zinc-400"
          >
            {colToLabel(col, snapshot)}
          </span>
        ))}
      </div>
      <div className="grid gap-3 lg:grid-cols-4">
        {stages.map((stage) => (
          <div key={stage.key} className="rounded-md border border-zinc-800/70 bg-zinc-900/35 p-2.5">
            <div className="mb-2 flex items-center gap-2">
              <span className="h-2 w-2 rounded-full" style={{ backgroundColor: stage.color }} />
              <span className="text-[11px] font-medium text-zinc-300">{stage.label}</span>
            </div>
            <div className="space-y-2">
              {[0, 1].map((i) => (
                <div key={i} className="rounded border border-zinc-800/60 bg-zinc-950/40 p-2">
                  <div className="h-2.5 w-2/3 rounded bg-zinc-800/80" />
                  <div className="mt-1.5 h-2 w-1/2 rounded bg-zinc-800/50" />
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <div className="rounded-md border border-zinc-800/60 bg-zinc-900/30 p-3">
          <p className="text-[11px] text-zinc-500">各公司在研数量（横条排序）</p>
          <div className="mt-2 space-y-1.5">
            {companyCols.slice(0, 4).map((col, i) => (
              <div key={col} className="flex items-center gap-2">
                <span className="w-14 shrink-0 text-[10px] text-zinc-500">{colToLabel(col, snapshot)}</span>
                <div className="h-2 flex-1 rounded bg-zinc-800/50">
                  <div
                    className="h-full rounded"
                    style={{
                      width: `${72 - i * 12}%`,
                      backgroundColor: BUSINESS_CHART_COLORS.current,
                      opacity: 0.55,
                    }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
        <div className="rounded-md border border-zinc-800/60 bg-zinc-900/30 p-3">
          <p className="text-[11px] text-zinc-500">类型分布（SLG / RPG / 休闲…）</p>
          <div className="mt-3 flex h-16 items-end gap-2">
            {["SLG", "RPG", "休闲", "其他"].map((t, i) => (
              <div key={t} className="flex flex-1 flex-col items-center gap-1">
                <div
                  className="w-full rounded-t"
                  style={{
                    height: `${28 + i * 10}px`,
                    backgroundColor: i % 2 === 0 ? BUSINESS_CHART_COLORS.current : "#d97706",
                    opacity: 0.45,
                  }}
                />
                <span className="text-[9px] text-zinc-600">{t}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </BlueprintShell>
  );
}

/** 运营产品矩阵可视化方案 */
export function OperatingProductsBlueprint({
  delayMs = 80,
  snapshot,
}: {
  delayMs?: number;
  snapshot?: CompetitorReportSnapshot;
}) {
  const companyCols = snapshot ? companyColsForSnapshot(snapshot) : [...COMPANY_COLS];
  const lifecycle = ["成熟期", "成长期", "衰退期", "新品"];
  return (
    <BlueprintShell
      title="运营产品矩阵"
      subtitle="展示各公司全部运营产品：品类标签、生命周期阶段、渠道/备注；数据完整后可叠加收入占比气泡。"
      delayMs={delayMs}
    >
      <div className="overflow-x-auto">
        <div className="min-w-[640px]">
          <div className="grid grid-cols-[88px_repeat(4,1fr)] gap-px rounded-md border border-zinc-800/70 bg-zinc-800/40 text-[10px]">
            <div className="bg-zinc-950/60 p-2 font-medium text-zinc-500">公司</div>
            {lifecycle.map((h) => (
              <div key={h} className="bg-zinc-950/60 p-2 text-center font-medium text-zinc-500">
                {h}
              </div>
            ))}
            {companyCols.slice(0, 4).map((col) => (
              <Fragment key={col}>
                <div className="bg-zinc-900/50 p-2 text-zinc-400">{colToLabel(col, snapshot)}</div>
                {lifecycle.map((lc, j) => (
                  <div key={`${col}-${lc}`} className="bg-zinc-900/35 p-2">
                    <div className="flex flex-wrap gap-1">
                      {(j < 2 ? [0, 1] : j === 2 ? [0] : []).map((k) => (
                        <span
                          key={k}
                          className="rounded border border-zinc-700/50 bg-zinc-950/50 px-1.5 py-0.5 text-[9px] text-zinc-500"
                        >
                          产品占位
                        </span>
                      ))}
                      {j >= 2 && j < 3 ? <span className="text-[9px] text-zinc-700">—</span> : null}
                    </div>
                  </div>
                ))}
              </Fragment>
            ))}
          </div>
        </div>
      </div>
      <p className="mt-3 text-[11px] text-zinc-600">
        备选视图：公司 × 品类热力格、产品清单可展开卡片、Top N 产品收入贡献横条（需补充明细字段）。
      </p>
    </BlueprintShell>
  );
}

/** 通用待补充小节占位 */
export function PendingSectionPanel({
  title,
  fields,
  hint,
  delayMs = 40,
}: {
  title: string;
  fields: string[];
  hint?: string;
  delayMs?: number;
}) {
  return (
    <BlueprintShell title={title} subtitle={hint ?? "数据/信息就绪后在此展示表格与图表。"} delayMs={delayMs}>
      <ul className="grid gap-2 sm:grid-cols-2">
        {fields.map((f) => (
          <li
            key={f}
            className="flex items-center gap-2 rounded-md border border-zinc-800/60 bg-zinc-900/40 px-3 py-2 text-xs text-zinc-500"
          >
            <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-zinc-600" />
            {f}
          </li>
        ))}
      </ul>
    </BlueprintShell>
  );
}
