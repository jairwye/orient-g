import { BUSINESS_CHART_COLORS } from "../../lib/business_chart_colors";
import { formatDecimal2, parseNum } from "./format";

export type DeltaTone = "up" | "down" | "neutral";

export type MetricDeltaDisplay = {
  amountText: string | null;
  rateText: string | null;
  tone: DeltaTone;
};

const PRESERVE_RATE = /扭亏|减亏|pct/i;

function toneFromDelta(n: number | null): DeltaTone {
  if (n == null || n === 0) return "neutral";
  return n > 0 ? "up" : "down";
}

function toneFromText(text: string): DeltaTone {
  const t = text.trim();
  if (!t || t === "—") return "neutral";
  if (/扭亏|减亏|增利|回升|改善/.test(t) && !/^-/.test(t)) return "up";
  if (/亏损|恶化|转亏|塌陷/.test(t)) return "down";
  const n = parseNum(t);
  if (n != null) return toneFromDelta(n);
  if (t.startsWith("+")) return "up";
  if (t.startsWith("-")) return "down";
  return "neutral";
}

/** 由当期与变动额推算同比（百分点） */
export function computeChangeRatePct(current: number, delta: number): number | null {
  const prev = current - delta;
  if (!Number.isFinite(prev) || prev === 0) return null;
  return Math.round((delta / Math.abs(prev)) * 10000) / 100;
}

function formatDeltaAmount(val: string | number | null | undefined): string | null {
  if (val == null || val === "") return null;
  if (typeof val === "string") {
    const t = val.trim();
    if (!t || t === "—") return null;
    if (/^[+-]/.test(t) || /,|，/.test(t)) return t;
  }
  const n = parseNum(val);
  if (n == null) return String(val);
  const sign = n > 0 ? "+" : n < 0 ? "" : "";
  return `${sign}${formatDecimal2(n)}`;
}

function formatRateText(val: string | number | null | undefined): string | null {
  if (val == null || val === "") return null;
  if (typeof val === "string") {
    const t = val.trim();
    if (!t || t === "—") return null;
    if (PRESERVE_RATE.test(t) || /%/.test(t) || /\(/.test(t)) return t;
  }
  const n = parseNum(val);
  if (n == null) return String(val);
  const pct = Math.abs(n) <= 1 ? n * 100 : n;
  const sign = pct > 0 ? "+" : "";
  return `${sign}${pct.toFixed(2)}%`;
}

function toneFromAmount(
  delta: string | number | null | undefined,
  amountText: string | null,
): DeltaTone {
  if (amountText) {
    const fromText = toneFromText(amountText);
    if (fromText !== "neutral") return fromText;
  }
  return toneFromDelta(parseNum(delta));
}

export function buildMetricDelta(
  delta: string | number | null | undefined,
  rate: string | number | null | undefined,
): MetricDeltaDisplay {
  const amountText = formatDeltaAmount(delta);
  const rateText = formatRateText(rate);
  const tone = amountText
    ? toneFromAmount(delta, amountText)
    : rateText
      ? toneFromText(rateText)
      : "neutral";

  return { amountText, rateText, tone };
}

export function deltaAccentColor(tone: DeltaTone): string {
  if (tone === "up") return BUSINESS_CHART_COLORS.actual;
  if (tone === "down") return "#ef4444";
  return "#71717a";
}
