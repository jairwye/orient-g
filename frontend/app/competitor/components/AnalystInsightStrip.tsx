"use client";

import type { AnalystInsight, InsightTone } from "../lib/finance_analysis";
import { FadeInView } from "./FadeInView";
import { CL } from "../lib/field_keys";

const TONE_STYLES: Record<InsightTone, string> = {
  positive: "border-emerald-900/50 bg-emerald-950/25 ring-emerald-900/30",
  warning: "border-amber-900/50 bg-amber-950/25 ring-amber-900/30",
  negative: "border-red-900/50 bg-red-950/25 ring-red-900/30",
  neutral: "border-zinc-800 bg-zinc-900/45 ring-zinc-800/60",
};

const TONE_LABEL: Record<InsightTone, string> = {
  positive: "text-emerald-300/90",
  warning: "text-amber-200/90",
  negative: "text-red-300/90",
  neutral: "text-blue-300/90",
};

export function AnalystInsightStrip({
  insights,
  delayMs = 0,
}: {
  insights: AnalystInsight[];
  delayMs?: number;
}) {
  if (!insights.length) return null;

  return (
    <FadeInView delayMs={delayMs}>
      <div className="space-y-2">
        <p className="text-xs font-medium tracking-wide text-zinc-500">{CL.analystView}</p>
        <div className="grid gap-3 md:grid-cols-3">
          {insights.map((item, i) => (
            <div
              key={`${item.label}-${i}`}
              className={`rounded-lg border p-3 ring-1 sm:p-3.5 ${TONE_STYLES[item.tone]}`}
            >
              <p className={`text-[10px] font-medium uppercase tracking-wider ${TONE_LABEL[item.tone]}`}>
                {item.label}
              </p>
              <p className="mt-1.5 text-sm font-medium leading-snug text-zinc-100">{item.headline}</p>
              {item.detail ? (
                <p className="mt-1.5 text-xs leading-relaxed text-zinc-400">{item.detail}</p>
              ) : null}
            </div>
          ))}
        </div>
      </div>
    </FadeInView>
  );
}
