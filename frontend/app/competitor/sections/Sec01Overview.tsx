"use client";

import { ChapterPanel } from "../components/ChapterPanel";
import { DataTable } from "../components/DataTable";
import { EmphasisLead } from "../components/NarrativeBlock";
import { MetricCardGrid } from "../components/MetricCards";
import { FadeInView } from "../components/FadeInView";
import { colToLabel } from "../lib/companies";
import { colorForCompany } from "../lib/competitor_chart_colors";
import { CL, FK } from "../lib/field_keys";
import { formatTableCell } from "../lib/format";
import { subTitleForSnap } from "../lib/navigation";
import { getNarrative, getTable } from "../lib/selectors";
import { type SectionProps } from "../lib/section_ui";

function BusinessModelCards({ snapshot }: { snapshot: SectionProps["snapshot"] }) {
  const table = getTable(snapshot, "sec-01-3");
  if (!table?.rows.length) return null;

  return (
    <div className="grid items-stretch gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {table.rows.map((row, i) => {
        const name = String(row[FK.company] ?? "");
        const keyword = String(row[FK.modeKeyword] ?? "");
        const feature = String(row[FK.coreFeature] ?? "");
        const accent = colorForCompany(name, snapshot);
        const displayName = colToLabel(name, snapshot);
        return (
          <FadeInView key={name || i} delayMs={i * 60} className="h-full">
            <div
              className="flex h-full flex-col rounded-lg border border-zinc-800 bg-zinc-900/50 p-4"
              style={{ borderTopColor: accent, borderTopWidth: 2 }}
            >
              <p className="text-sm font-medium text-zinc-200">{displayName}</p>
              <p className="mt-1 text-xs" style={{ color: accent }}>
                {keyword}
              </p>
              <p className="mt-2 flex-1 text-xs leading-relaxed text-zinc-500">{feature}</p>
            </div>
          </FadeInView>
        );
      })}
    </div>
  );
}

export function Sec01Overview({ snapshot }: SectionProps) {
  const landscapeNarrative = getNarrative(snapshot, "sec-01-1");
  const metricsTable = getTable(snapshot, "sec-01-1");
  const kpiTable = getTable(snapshot, "sec-01-2");

  return (
    <ChapterPanel
      sectionId="sec-01"
      slides={[
        {
          id: "sec-01-a",
          title: subTitleForSnap("sec-01-a"),
          spacious: true,
          hero: true,
          content: (
            <div className="space-y-10 sm:space-y-12">
              {landscapeNarrative?.markdown ? (
                <EmphasisLead text={landscapeNarrative.markdown} />
              ) : null}
              {metricsTable?.rows ? (
                <MetricCardGrid rows={metricsTable.rows} prominent />
              ) : null}
            </div>
          ),
        },
        {
          id: "sec-01-b",
          title: subTitleForSnap("sec-01-b"),
          content: (
            <div className="space-y-8 sm:space-y-10">
              {kpiTable?.rows ? (
                <DataTable
                  title={CL.companyKpi}
                  headers={kpiTable.headers}
                  rows={kpiTable.rows}
                  compact
                  rowAccent={(row) => colorForCompany(String(row[FK.company] ?? ""), snapshot)}
                  formatCell={(h, v) =>
                    h === FK.company ? colToLabel(String(v ?? ""), snapshot) : formatTableCell(h, v)
                  }
                />
              ) : null}
              <div className="space-y-4">
                <h3 className="text-sm font-medium text-zinc-400">{CL.businessModel}</h3>
                <BusinessModelCards snapshot={snapshot} />
              </div>
            </div>
          ),
        },
      ]}
    />
  );
}
