"use client";

import { colToLabel } from "../lib/companies";
import { colorForCompany } from "../lib/competitor_chart_colors";
import { FK } from "../lib/field_keys";
import { formatTableCell } from "../lib/format";
import type { CompetitorReportSnapshot } from "../lib/types";
import { FadeInView } from "./FadeInView";

const QUADRANT_ACCENT: Record<string, string> = {
  量利齐升: "#22c55e",
  减收增利: "#2563eb",
  减收减利: "#d97706",
  "亏损/高风险": "#ef4444",
};

type Row = Record<string, string | number | null>;

export function QuadrantGrid({ rows, delayMs = 0 }: { rows: Row[]; delayMs?: number }) {
  if (!rows.length) return null;

  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {rows.map((row, i) => {
        const quadrant = String(row["象限"] ?? "");
        const companies = String(row["公司"] ?? "");
        const feature = String(row["特征"] ?? "");
        const accent = QUADRANT_ACCENT[quadrant] ?? "#52525b";
        return (
          <FadeInView key={i} delayMs={delayMs + i * 60} immediate>
            <div
              className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 md:p-5"
              style={{ borderTopColor: accent, borderTopWidth: 2 }}
            >
              <p className="text-sm font-medium" style={{ color: accent }}>
                {quadrant}
              </p>
              <p className="mt-1 text-base font-medium text-zinc-100">{companies}</p>
              <p className="mt-2 text-sm leading-relaxed text-zinc-500">{feature}</p>
            </div>
          </FadeInView>
        );
      })}
    </div>
  );
}

export function RankInsightCards({
  rows,
  snapshot,
  fillHeight = false,
  delayMs = 80,
}: {
  rows: Row[];
  snapshot: CompetitorReportSnapshot;
  fillHeight?: boolean;
  delayMs?: number;
}) {
  if (!rows.length) return null;

  const gridClass = fillHeight
    ? "grid h-full min-h-0 grid-cols-2 grid-rows-4 gap-1.5 sm:gap-2"
    : "grid gap-3 md:grid-cols-2";

  return (
    <div className={gridClass}>
      {rows.map((row, i) => {
        const rawName = String(row[FK.company] ?? "");
        const name = colToLabel(rawName, snapshot);
        const tag = String(row[FK.tag] ?? row["标签"] ?? "");
        const insight = String(row[FK.oneLine] ?? row["一句话研判"] ?? "");
        const scoreRaw = row[FK.compositeScore] ?? row["综合评分"];
        const score = formatTableCell(FK.compositeScore, scoreRaw);
        const rankRaw = row["排名"];
        const rank =
          rankRaw != null && rankRaw !== ""
            ? formatTableCell("排名", rankRaw)
            : String(i + 1);
        const accent = colorForCompany(rawName, snapshot);

        return (
          <FadeInView key={rawName || i} delayMs={delayMs + i * 40} immediate={!fillHeight}>
            <article
              className={
                "flex h-full min-h-0 flex-col rounded-md border border-zinc-800/80 bg-zinc-950/35 p-2.5 sm:p-3 " +
                (fillHeight ? "justify-start" : "")
              }
              style={{ borderLeftColor: accent, borderLeftWidth: 3 }}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex min-w-0 items-center gap-1.5">
                  <span className="shrink-0 text-xs font-semibold tabular-nums text-zinc-500">#{rank}</span>
                  <h4 className="truncate text-sm font-medium text-zinc-100">{name}</h4>
                  {tag ? (
                    <span className="hidden shrink-0 rounded border border-zinc-700/80 bg-zinc-900/80 px-1.5 py-0.5 text-[10px] text-zinc-400 sm:inline">
                      {tag}
                    </span>
                  ) : null}
                </div>
                <p className="shrink-0 text-base font-bold tabular-nums text-zinc-100 sm:text-lg">{score}</p>
              </div>
              {tag ? (
                <span className="mt-1 inline-flex w-fit rounded border border-zinc-700/80 bg-zinc-900/80 px-1.5 py-0.5 text-[10px] text-zinc-400 sm:hidden">
                  {tag}
                </span>
              ) : null}
              {insight ? (
                <p className="mt-1.5 text-xs leading-relaxed text-zinc-400 sm:text-sm sm:leading-relaxed">{insight}</p>
              ) : null}
            </article>
          </FadeInView>
        );
      })}
    </div>
  );
}
