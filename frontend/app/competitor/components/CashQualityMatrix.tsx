"use client";

import type { CashQualityPoint } from "../lib/finance_analysis";
import { colorForCompany } from "../lib/competitor_chart_colors";
import type { CompetitorReportSnapshot } from "../lib/types";
import { CL } from "../lib/field_keys";
import { formatPctPoints, formatYiWan } from "../lib/format";
import { FadeInView } from "./FadeInView";

const TIER_BADGE: Record<CashQualityPoint["tier"], string> = {
  A: "bg-emerald-900/55 text-emerald-100 ring-emerald-800/50",
  B: "bg-blue-900/40 text-blue-100 ring-blue-800/45",
  C: "bg-amber-900/40 text-amber-100 ring-amber-800/45",
  D: "bg-red-900/50 text-red-100 ring-red-900/50",
};

export function CashQualityMatrix({
  points,
  snapshot,
  delayMs = 0,
}: {
  points: CashQualityPoint[];
  snapshot: CompetitorReportSnapshot;
  delayMs?: number;
}) {
  if (!points.length) return null;

  return (
    <FadeInView delayMs={delayMs}>
      <div className="rounded-lg border border-zinc-800/80 bg-zinc-900/45 p-3 sm:p-4">
        <h3 className="mb-3 text-sm font-medium text-zinc-300">{CL.cashQualityMatrix}</h3>
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          {points.map((p) => (
            <div
              key={p.colKey}
              className="rounded-md border border-zinc-800/70 bg-zinc-950/40 p-3"
              style={{ borderTopColor: colorForCompany(p.colKey, snapshot), borderTopWidth: 2 }}
            >
              <div className="flex items-start justify-between gap-2">
                <p className="text-sm font-medium text-zinc-100">{p.name}</p>
                <span className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-bold ring-1 ${TIER_BADGE[p.tier]}`}>
                  {p.tier}
                </span>
              </div>
              <p className="mt-1 text-[11px] leading-snug text-zinc-400">{p.tierLabel}</p>
              <dl className="mt-2 space-y-1 text-[11px] tabular-nums">
                <div className="flex justify-between gap-2 text-zinc-500">
                  <dt>{CL.netProfit}</dt>
                  <dd className="text-zinc-300">{formatYiWan(p.profit)}</dd>
                </div>
                <div className="flex justify-between gap-2 text-zinc-500">
                  <dt>{CL.ocf}</dt>
                  <dd className="text-zinc-300">{formatYiWan(p.ocf)}</dd>
                </div>
                <div className="flex justify-between gap-2 text-zinc-500">
                  <dt>{CL.ocfRatio}</dt>
                  <dd className="text-zinc-300">{formatPctPoints(p.ratioPct)}</dd>
                </div>
              </dl>
            </div>
          ))}
        </div>
      </div>
    </FadeInView>
  );
}
