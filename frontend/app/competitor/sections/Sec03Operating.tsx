"use client";

import { ChapterPanel } from "../components/ChapterPanel";
import { OperatingOverviewSlide } from "../components/OperatingOverviewSlide";
import { subTitleForSnap } from "../lib/navigation";
import { getTable } from "../lib/selectors";
import { type SectionProps } from "../lib/section_ui";

export function Sec03Operating({ snapshot }: SectionProps) {
  const sec03 = snapshot.sections.find((s) => s.id === "sec-03");
  const core = getTable(snapshot, "sec-03-1");
  const quadrant = getTable(snapshot, "sec-03-3");

  const overviewContent =
    core?.rows && core.rows.length > 0 ? (
      <OperatingOverviewSlide
        rows={core.rows}
        snapshot={snapshot}
        blocks={sec03?.blocks ?? []}
        quadrantRows={quadrant?.rows}
        headerKeys={core.header_keys}
        headers={core.headers}
      />
    ) : null;

  return (
    <ChapterPanel
      sectionId="sec-03"
      slides={[
        {
          id: "sec-03-a",
          title: subTitleForSnap("sec-03-a"),
          dense: true,
          content: overviewContent,
        },
      ]}
    />
  );
}
