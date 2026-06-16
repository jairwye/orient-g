"use client";

import type { CompetitorReportSnapshot } from "../lib/types";
import { CL } from "../lib/field_keys";
import { CompanyMetricGrid } from "./CompanyMetricGrid";
import { QuadrantGrid } from "./InsightCards";
import { NarrativesFromSection } from "./NarrativeBlock";

type Row = Record<string, string | number | null>;

function SectionHeading({ id, label }: { id: string; label: string }) {
  return (
    <div className="mb-3 flex items-center gap-3 md:mb-4">
      <h3 id={id} className="text-xs font-medium uppercase tracking-[0.14em] text-zinc-500">
        {label}
      </h3>
      <span className="h-px flex-1 bg-gradient-to-r from-zinc-700/80 to-transparent" />
    </div>
  );
}

/** sec-03 指标卡 + 经营结论 + 三维交叉验证（第四屏） */
export function OperatingOverviewSlide({
  rows,
  snapshot,
  blocks,
  quadrantRows,
}: {
  rows: Row[];
  snapshot: CompetitorReportSnapshot;
  blocks: Array<{ kind: string; markdown?: string; anchor?: string }>;
  quadrantRows?: Row[];
}) {
  return (
    <div className="flex flex-col gap-6 lg:gap-7">
      <section aria-labelledby="operating-metrics-heading">
        <SectionHeading id="operating-metrics-heading" label={CL.operatingCoreData} />
        <CompanyMetricGrid rows={rows} snapshot={snapshot} dense />
      </section>

      <section aria-labelledby="operating-conclusion-heading">
        <SectionHeading id="operating-conclusion-heading" label={CL.operatingConclusion} />
        <NarrativesFromSection blocks={blocks} anchor="sec-03-2" immediate plain stripAnalysisPrefix />
      </section>

      {quadrantRows && quadrantRows.length > 0 ? (
        <section aria-labelledby="operating-quadrant-heading">
          <SectionHeading id="operating-quadrant-heading" label={CL.operatingQuadrant} />
          <QuadrantGrid rows={quadrantRows} delayMs={120} />
        </section>
      ) : null}
    </div>
  );
}
