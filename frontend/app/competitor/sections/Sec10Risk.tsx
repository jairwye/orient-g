"use client";

import { Fragment, useMemo } from "react";
import { AnalystInsightStrip } from "../components/AnalystInsightStrip";
import { ChapterPanel } from "../components/ChapterPanel";
import { ChartPanel } from "../components/ChartPanel";
import { DataTable } from "../components/DataTable";
import { FadeInView } from "../components/FadeInView";
import { NarrativesFromSection } from "../components/NarrativeBlock";
import {
  deriveRiskInsights,
  deriveRndCapInsights,
  deriveSubsidiaryInsights,
} from "../lib/finance_analysis";
import { CL, FK } from "../lib/field_keys";
import { subTitleForSnap } from "../lib/navigation";
import { getTable } from "../lib/selectors";
import { type SectionProps } from "../lib/section_ui";

const RISK_LEVEL: Record<string, string> = {
  [FK.riskLow]: "bg-emerald-900/50 text-emerald-200 ring-emerald-800/40",
  [FK.riskMid]: "bg-amber-900/45 text-amber-100 ring-amber-800/40",
  [FK.riskHigh]: "bg-red-900/50 text-red-200 ring-red-900/50",
  [FK.riskExtreme]: "bg-red-950/70 text-red-100 ring-red-900/60",
  [FK.riskGood]: "bg-blue-900/35 text-blue-100 ring-blue-800/40",
  [FK.riskExcellent]: "bg-blue-900/50 text-blue-50 ring-blue-700/40",
  [FK.riskBad]: "bg-red-900/55 text-red-100 ring-red-900/50",
  [FK.riskFair]: "bg-orange-900/45 text-orange-100 ring-orange-800/40",
  [FK.riskInflated]: "bg-zinc-800/80 text-zinc-300 ring-zinc-700/50",
  [FK.riskPersistent]: "bg-red-950 text-red-100 ring-red-900/60",
};

const LEGEND_ITEMS: Array<{ label: string; cls: string }> = [
  { label: FK.riskExcellent, cls: RISK_LEVEL[FK.riskExcellent] },
  { label: FK.riskGood, cls: RISK_LEVEL[FK.riskGood] },
  { label: FK.riskLow, cls: RISK_LEVEL[FK.riskLow] },
  { label: FK.riskMid, cls: RISK_LEVEL[FK.riskMid] },
  { label: FK.riskFair, cls: RISK_LEVEL[FK.riskFair] },
  { label: FK.riskHigh, cls: RISK_LEVEL[FK.riskHigh] },
  { label: FK.riskBad, cls: RISK_LEVEL[FK.riskBad] },
  { label: FK.riskExtreme, cls: RISK_LEVEL[FK.riskExtreme] },
];

function cellClass(v: string): string {
  const key = v.trim();
  for (const [k, cls] of Object.entries(RISK_LEVEL)) {
    if (key.includes(k)) return cls;
  }
  return "bg-zinc-900/80 text-zinc-400 ring-zinc-800/50";
}

export function Sec10Risk({ snapshot }: SectionProps) {
  const sec10 = snapshot.sections.find((s) => s.id === "sec-10");
  const risk = getTable(snapshot, "sec-10-1");
  const rnd = getTable(snapshot, "sec-10-2");
  const subsidiary = getTable(snapshot, "sec-10-3");
  const summary = getTable(snapshot, "sec-10-4");

  const riskInsights = useMemo(() => deriveRiskInsights(snapshot), [snapshot]);
  const rndInsights = useMemo(() => deriveRndCapInsights(snapshot), [snapshot]);
  const subInsights = useMemo(() => deriveSubsidiaryInsights(snapshot), [snapshot]);

  const companies = risk?.headers.filter((h) => h !== FK.riskDim) ?? [];
  const rows = risk?.rows ?? [];

  const heatmap =
    rows.length > 0 ? (
      <ChartPanel title={CL.riskCard} delayMs={100} height="h-auto min-h-[320px]">
        <FadeInView delayMs={120}>
          <div className="mb-4 flex flex-wrap gap-2">
            <span className="w-full text-xs font-medium text-zinc-500 sm:w-auto">{CL.riskLegend}</span>
            {LEGEND_ITEMS.map(({ label, cls }) => (
              <span key={label} className={`rounded-md px-2 py-0.5 text-[10px] ring-1 ${cls}`}>
                {label}
              </span>
            ))}
          </div>
          <div className="overflow-x-auto">
            <div
              className="grid min-w-[680px] gap-1.5 text-center text-xs"
              style={{ gridTemplateColumns: `minmax(108px,128px) repeat(${companies.length}, minmax(76px, 1fr))` }}
            >
              <div className="sticky left-0 z-10 bg-zinc-900/95 p-2 text-left font-medium text-zinc-500">{CL.dim}</div>
              {companies.map((d) => (
                <div key={d} className="p-2 text-[11px] font-medium leading-tight text-zinc-400">
                  {d === "YYCQ" ? FK.yycqLabel : d}
                </div>
              ))}
              {rows.map((row, ri) => (
                <Fragment key={ri}>
                  <div className="sticky left-0 z-10 flex items-center bg-zinc-900/95 p-2 text-left text-sm leading-snug text-zinc-200">
                    {String(row[FK.riskDim] ?? "")}
                  </div>
                  {companies.map((d) => {
                    const val = String(row[d] ?? "\u2014");
                    return (
                      <div
                        key={`${ri}-${d}`}
                        title={`${row[FK.riskDim]} · ${d === "YYCQ" ? FK.yycqLabel : d}: ${val}`}
                        className={`flex min-h-[2.5rem] items-center justify-center rounded-md p-2 text-[11px] font-medium leading-tight ring-1 transition-transform duration-200 hover:scale-[1.03] ${cellClass(val)}`}
                      >
                        {val}
                      </div>
                    );
                  })}
                </Fragment>
              ))}
            </div>
          </div>
        </FadeInView>
      </ChartPanel>
    ) : null;

  return (
    <ChapterPanel
      sectionId="sec-10"
      slides={[
        {
          id: "sec-10-a",
          title: subTitleForSnap("sec-10-a"),
          content: (
            <>
              <AnalystInsightStrip insights={riskInsights} />
              {risk ? (
                <DataTable title={CL.riskScorecard} headers={risk.headers} rows={risk.rows} delayMs={60} compact />
              ) : null}
              <div className="mt-5">{heatmap}</div>
            </>
          ),
        },
        {
          id: "sec-10-b",
          title: subTitleForSnap("sec-10-b"),
          content: (
            <>
              <AnalystInsightStrip insights={rndInsights} delayMs={40} />
              {rnd && rnd.rows.length > 0 ? (
                <DataTable title={CL.rndCapital} headers={rnd.headers} rows={rnd.rows} delayMs={60} compact />
              ) : null}
            </>
          ),
        },
        {
          id: "sec-10-c",
          title: subTitleForSnap("sec-10-c"),
          content: (
            <>
              <AnalystInsightStrip insights={subInsights} delayMs={40} />
              {subsidiary && subsidiary.rows.length > 0 ? (
                <DataTable title={CL.subsidiaryContrib} headers={subsidiary.headers} rows={subsidiary.rows} delayMs={60} compact />
              ) : null}
            </>
          ),
        },
        {
          id: "sec-10-d",
          title: subTitleForSnap("sec-10-d"),
          content: (
            <>
              {summary && summary.rows.length > 0 ? (
                <DataTable title={CL.industrySummary} headers={summary.headers} rows={summary.rows} delayMs={40} compact />
              ) : null}
              <div className="mt-5 sm:mt-6">
                <NarrativesFromSection blocks={sec10?.blocks ?? []} anchor="sec-10-4" plain stripAnalysisPrefix />
              </div>
            </>
          ),
        },
      ]}
    />
  );
}
