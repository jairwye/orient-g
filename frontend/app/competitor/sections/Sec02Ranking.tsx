"use client";

import { ChapterPanel } from "../components/ChapterPanel";
import { ChartPanel } from "../components/ChartPanel";
import { RankInsightCards } from "../components/InsightCards";
import { firstNarrativeLead } from "../components/NarrativeBlock";
import { RadarFiveChart } from "../components/RadarFiveChart";
import { CL } from "../lib/field_keys";
import { subTitleForSnap } from "../lib/navigation";
import { getTable } from "../lib/selectors";
import { type SectionProps } from "../lib/section_ui";

export function Sec02Ranking({ snapshot }: SectionProps) {
  const sec02 = snapshot.sections.find((s) => s.id === "sec-02");
  const rankTable = getTable(snapshot, "sec-02-1");
  const radarTable = getTable(snapshot, "sec-02-2");
  const lead = firstNarrativeLead(sec02?.blocks ?? []);

  const panelHeight = "h-[min(560px,74vh)]";

  return (
    <ChapterPanel
      sectionId="sec-02"
      lead={lead}
      sectionNote={CL.scoreMethodBody}
      slides={[
        {
          id: "sec-02-a",
          title: subTitleForSnap("sec-02-a"),
          content: (
            <div className="grid min-h-0 flex-1 gap-5 lg:grid-cols-2 lg:gap-6">
              {rankTable?.rows ? (
                <ChartPanel title={CL.compositeScore} delayMs={80} height={panelHeight}>
                  <RankInsightCards
                    rows={rankTable.rows}
                    snapshot={snapshot}
                    fillHeight
                    delayMs={80}
                  />
                </ChartPanel>
              ) : null}
              {radarTable?.rows ? (
                <ChartPanel title={CL.radarFive} delayMs={140} height={panelHeight}>
                  <RadarFiveChart snapshot={snapshot} rows={radarTable.rows} />
                </ChartPanel>
              ) : null}
            </div>
          ),
        },
      ]}
    />
  );
}
