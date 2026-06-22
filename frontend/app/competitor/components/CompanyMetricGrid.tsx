"use client";

import { colToLabel } from "../lib/companies";
import { colorForCompany } from "../lib/competitor_chart_colors";
import type { CompetitorReportSnapshot } from "../lib/types";
import { CL, FK } from "../lib/field_keys";
import { buildMetricDelta } from "../lib/metric_delta";
import { formatPct, formatYiWan, parseNum } from "../lib/format";
import { FadeInView } from "./FadeInView";
import { MetricDeltaBadge } from "./MetricDeltaBadge";

type Row = Record<string, string | number | null>;

const REV_DELTA = "\u8425\u6536\u53d8\u52a8";
const PROFIT_DELTA = "\u51c0\u5229\u53d8\u52a8";
const CHANGE_RATE = "\u53d8\u52a8\u7387";
const ROE_KEY = "ROE";
const ROE_DELTA = "ROE\u53d8\u52a8";

function MetricRow({
  label,
  value,
  valueClassName = "text-zinc-100",
  delta,
  dense = false,
}: {
  label: string;
  value: string;
  valueClassName?: string;
  delta: ReturnType<typeof buildMetricDelta>;
  dense?: boolean;
}) {
  const hasDelta = delta.amountText || delta.rateText;
  return (
    <div className="relative">
      {hasDelta ? (
        <div className="absolute right-0 top-0 max-w-[58%]">
          <MetricDeltaBadge delta={delta} compact />
        </div>
      ) : null}
      <p className="text-[10px] uppercase tracking-wide text-zinc-500">{label}</p>
      <p
        className={
          "mt-0.5 font-bold tabular-nums tracking-tight " +
          (dense ? "text-base sm:text-lg" : "text-xl sm:text-2xl") +
          " " +
          valueClassName
        }
      >
        {value}
      </p>
    </div>
  );
}

export function CompanyMetricGrid({
  rows,
  snapshot,
  dense = false,
}: {
  rows: Row[];
  snapshot: CompetitorReportSnapshot;
  /** 与叙事同屏时使用更紧凑卡片 */
  dense?: boolean;
}) {
  return (
    <div
      className={
        "mx-auto grid w-full items-stretch " +
        (dense ? "gap-2.5 sm:grid-cols-2 lg:grid-cols-4 lg:gap-3" : "gap-4 sm:grid-cols-2 xl:grid-cols-4")
      }
    >
      {rows.map((row, i) => {
        const name = String(row[FK.company] ?? "");
        const revenue = parseNum(row[FK.revenueWan]);
        const profit = parseNum(row[FK.profitWan]);
        const roe = parseNum(row[ROE_KEY]);
        const accent = colorForCompany(name, snapshot);
        const profitPositive = profit != null && profit >= 0;
        const displayName = colToLabel(name, snapshot);

        const revDeltaRaw = row[REV_DELTA];
        const revDeltaNum = typeof revDeltaRaw === "number" ? revDeltaRaw : parseNum(revDeltaRaw);
        const revenueDelta = buildMetricDelta(revDeltaRaw, null, {
          current: revenue,
          computeRate: revenue != null && revDeltaNum != null,
        });

        const profitDelta = buildMetricDelta(row[PROFIT_DELTA], row[CHANGE_RATE]);

        return (
          <FadeInView key={name || i} delayMs={i * 40} className="h-full" immediate>
            <div
              className={
                "flex h-full flex-col rounded-lg border border-zinc-800 bg-zinc-900/50 " +
                (dense ? "min-h-[148px] p-3.5 sm:p-4" : "min-h-[200px] p-5")
              }
              style={{ borderTopColor: accent, borderTopWidth: 2 }}
            >
              <p className={dense ? "text-xs font-medium text-zinc-200" : "text-sm font-medium text-zinc-200"}>
                {displayName}
              </p>
              <div
                className={
                  "mt-3 flex flex-1 flex-col justify-between " + (dense ? "gap-3" : "mt-4 gap-5")
                }
              >
                <MetricRow
                  label={CL.revenue}
                  value={formatYiWan(revenue)}
                  delta={revenueDelta}
                  dense={dense}
                />
                <MetricRow
                  label={CL.profit}
                  value={formatYiWan(profit)}
                  valueClassName={
                    profitPositive ? "text-green-500" : profit != null ? "text-red-400" : "text-zinc-100"
                  }
                  delta={profitDelta}
                  dense={dense}
                />
                {roe != null ? (
                  <div>
                    <p className="text-[10px] uppercase tracking-wide text-zinc-500">ROE</p>
                    <div className="mt-0.5 flex flex-wrap items-center gap-2">
                      <p
                        className={
                          "font-semibold tabular-nums text-zinc-100 " +
                          (dense ? "text-sm" : "text-lg")
                        }
                      >
                        {formatPct(roe)}
                      </p>
                      {row[ROE_DELTA] ? (
                        <MetricDeltaBadge
                          delta={{
                            amountText: String(row[ROE_DELTA]),
                            rateText: null,
                            tone: buildMetricDelta(row[ROE_DELTA], null).tone,
                          }}
                          compact
                        />
                      ) : null}
                    </div>
                  </div>
                ) : null}
              </div>
            </div>
          </FadeInView>
        );
      })}
    </div>
  );
}
