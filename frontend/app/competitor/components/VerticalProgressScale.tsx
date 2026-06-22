"use client";

import { useMemo } from "react";
import { buildVerticalScaleEntries } from "../lib/vertical_navigation";
import type { VerticalReportSnapshot } from "../lib/vertical_types";
import type { CompetitorReportSnapshot } from "../lib/types";

type Props = {
  report: VerticalReportSnapshot;
  competitorSnapshot?: CompetitorReportSnapshot;
  activeSnapId: string;
  onNavigate: (id: string) => void;
};

/** 纵向对比页顶刻度：圆点 + 公司名（蓝本展示名） */
export function VerticalProgressScale({ report, competitorSnapshot, activeSnapId, onNavigate }: Props) {
  const entries = useMemo(
    () => buildVerticalScaleEntries(report, competitorSnapshot),
    [report, competitorSnapshot],
  );

  return (
    <nav
      className="hidden w-[min(72vw,640px)] shrink-0 sm:block"
      aria-label="公司导航"
      data-active-snap={activeSnapId}
    >
      <div className="ml-auto flex items-start justify-end gap-0.5 md:gap-1">
        {entries.map((entry) => {
          const isActive = activeSnapId === entry.snapId;
          return (
            <button
              key={entry.snapId}
              type="button"
              data-testid={`snap-dot-${entry.snapId}`}
              data-active={isActive ? "true" : "false"}
              aria-label={entry.fullLabel}
              aria-current={isActive ? "true" : undefined}
              onClick={() => onNavigate(entry.snapId)}
              className="group/dot flex min-w-0 flex-1 flex-col items-center gap-1.5 px-0.5 py-1"
            >
              <span
                className={
                  "block shrink-0 rounded-full transition-colors duration-200 " +
                  (isActive
                    ? "h-2.5 w-2.5 bg-blue-600 shadow-[0_0_10px_rgba(37,99,235,0.5)]"
                    : "h-2 w-2 border border-zinc-600 bg-zinc-800 group-hover/dot:border-zinc-400")
                }
              />
              <span
                className={
                  "w-full text-center text-[10px] leading-tight sm:text-[11px] " +
                  (isActive ? "font-medium text-blue-200" : "text-zinc-500 group-hover/dot:text-zinc-400")
                }
              >
                {entry.fullLabel}
              </span>
            </button>
          );
        })}
      </div>
    </nav>
  );
}
