"use client";

import { TrendingDown, TrendingUp } from "lucide-react";
import type { MetricDeltaDisplay } from "../lib/metric_delta";
import { deltaAccentColor } from "../lib/metric_delta";

export function MetricDeltaBadge({
  delta,
  compact = false,
}: {
  delta: MetricDeltaDisplay;
  compact?: boolean;
}) {
  const { amountText, rateText, tone } = delta;
  if (!amountText && !rateText) return null;

  const color = deltaAccentColor(tone);
  const showUp = tone === "up";
  const showDown = tone === "down";

  return (
    <div
      className={
        "flex flex-wrap items-center gap-1 rounded border border-zinc-800 bg-zinc-950 tabular-nums text-zinc-300 " +
        (compact ? "px-1.5 py-0.5 text-[10px]" : "px-2 py-1 text-xs font-medium")
      }
    >
      {showUp && <TrendingUp className={compact ? "h-3 w-3" : "h-3.5 w-3.5"} style={{ color }} />}
      {showDown && <TrendingDown className={compact ? "h-3 w-3" : "h-3.5 w-3.5"} style={{ color }} />}
      {amountText ? <span style={{ color: tone !== "neutral" ? color : undefined }}>{amountText}</span> : null}
      {amountText && rateText ? <span className="text-zinc-600">·</span> : null}
      {rateText ? <span>{rateText}</span> : null}
    </div>
  );
}
