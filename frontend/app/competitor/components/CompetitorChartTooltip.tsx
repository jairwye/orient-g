"use client";

import type { ReactNode } from "react";
import { Tooltip, type TooltipProps } from "recharts";
import { CHART_BAR_CURSOR, CHART_NO_CURSOR, CHART_SCATTER_CURSOR } from "../lib/competitor_chart_colors";
import { formatDecimal2 } from "../lib/format";

type PayloadItem = {
  name: string;
  value: number;
  dataKey: string;
  color?: string;
  payload?: Record<string, unknown>;
};

type Props = {
  active?: boolean;
  payload?: PayloadItem[];
  label?: string | number;
  /** 自定义数值格式化；返回展示字符串 */
  valueFormatter?: (value: number, name: string, dataKey: string) => string;
};

/** Recharts 须直接使用 <Tooltip />，不可用包装组件（否则 hover 失效） */
export function competitorBarTooltipProps(
  props: Omit<TooltipProps<number, string>, "cursor">,
): TooltipProps<number, string> {
  return { ...props, cursor: CHART_BAR_CURSOR };
}

export function competitorPieTooltipProps(
  props: Omit<TooltipProps<number, string>, "cursor">,
): TooltipProps<number, string> {
  return { ...props, cursor: CHART_NO_CURSOR };
}

export function competitorScatterTooltipProps(
  props: Omit<TooltipProps<number, string>, "cursor">,
): TooltipProps<number, string> {
  return { ...props, cursor: CHART_SCATTER_CURSOR };
}

/** @deprecated 请用 <Tooltip {...competitorBarTooltipProps({ content })} /> */
export function CompetitorBarTooltip(props: Omit<TooltipProps<number, string>, "cursor">) {
  return <Tooltip {...competitorBarTooltipProps(props)} />;
}

/** 与经营数据页 BusinessDashboard ChartTooltip 一致 */
export function CompetitorChartTooltip({
  active,
  payload,
  label,
  valueFormatter,
}: Props) {
  if (!active || !payload?.length) return null;

  const shell = (children: ReactNode) => (
    <div className="rounded-md border border-zinc-600 bg-zinc-900 px-3 py-2 shadow-lg">{children}</div>
  );

  const row = payload[0]?.payload as Record<string, unknown> | undefined;

  /** 杜邦散点 / ROE 柱图：payload 含 name / roe / netMargin / turnover / leverage */
  if (
    row &&
    typeof row.name === "string" &&
    typeof row.roe === "number" &&
    (typeof row.netMargin === "number" ||
      typeof row.turnover === "number" ||
      typeof row.leverage === "number")
  ) {
    return shell(
      <>
        <p className="mb-1.5 text-xs font-medium text-zinc-300">{row.name}</p>
        <ul className="space-y-0.5 text-sm tabular-nums text-zinc-100">
          <li>ROE：{formatPct(row.roe)}</li>
          {typeof row.netMargin === "number" ? <li>净利率：{formatPct(row.netMargin)}</li> : null}
          {typeof row.turnover === "number" ? (
            <li>总资产周转率：{Number(row.turnover).toFixed(2)}x</li>
          ) : null}
          {typeof row.leverage === "number" ? (
            <li>权益乘数：{Number(row.leverage).toFixed(2)}x</li>
          ) : null}
          {typeof row.driverLabel === "string" ? (
            <li className="text-xs text-zinc-400">{row.driverLabel}</li>
          ) : null}
        </ul>
      </>,
    );
  }

  /** 商业模式散点：gross × sales */
  if (row && typeof row.name === "string" && typeof row.gross === "number" && typeof row.sales === "number") {
    return shell(
      <>
        <p className="mb-1.5 text-xs font-medium text-zinc-300">{row.name}</p>
        <ul className="space-y-0.5 text-sm tabular-nums text-zinc-100">
          <li>毛利率：{formatPct(row.gross)}</li>
          <li>销售费用率：{formatPct(row.sales)}</li>
          {typeof row.opMargin === "number" ? (
            <li>隐含营业利润率：{formatPct(row.opMargin)}</li>
          ) : null}
        </ul>
      </>,
    );
  }

  const displayLabel =
    label != null && label !== ""
      ? String(label)
      : typeof row?.name === "string"
        ? row.name
        : typeof row?.label === "string"
          ? row.label
          : "";

  return shell(
    <>
      {displayLabel ? <p className="mb-1.5 text-xs font-medium text-zinc-400">{displayLabel}</p> : null}
      <ul className="space-y-0.5 text-sm tabular-nums text-zinc-100">
        {payload.map((entry) => {
          const val = entry.value ?? (entry.payload?.[entry.dataKey] as number | undefined);
          if (val == null || !Number.isFinite(Number(val))) return null;
          const name =
            entry.name && entry.name !== entry.dataKey
              ? entry.name
              : String(entry.dataKey ?? "值");
          return (
            <li key={`${entry.dataKey}-${name}`} className="flex items-center gap-2">
              {entry.color ? (
                <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: entry.color }} />
              ) : null}
              <span>
                {name}：{" "}
                {valueFormatter
                  ? valueFormatter(Number(val), name, entry.dataKey)
                  : formatDecimal2(Number(val))}
              </span>
            </li>
          );
        })}
      </ul>
    </>
  );
}

function formatPct(n: number): string {
  if (!Number.isFinite(n)) return "—";
  return `${n.toFixed(1)}%`;
}
