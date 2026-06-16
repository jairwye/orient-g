import type { ReactNode } from "react";
import type { CompetitorReportSnapshot } from "./types";
import { EmphasisLead } from "../components/NarrativeBlock";
import { FadeInView } from "../components/FadeInView";
import { NAV_SECTIONS } from "./navigation";

export function sectionTitleById(sectionId: string): string {
  return NAV_SECTIONS.find((s) => s.id === sectionId)?.title ?? sectionId;
}

export type SectionProps = {
  snapshot: CompetitorReportSnapshot;
};

export function SectionHeader({
  sectionId,
  title,
  lead,
  note,
}: {
  sectionId: string;
  title?: string;
  lead?: string;
  /** 标题下小字说明（如评分方法） */
  note?: string;
}) {
  const resolvedTitle = title ?? sectionTitleById(sectionId);
  return (
    <FadeInView>
      <div className="max-w-4xl pt-6 sm:pt-8 md:pt-10">
        <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-zinc-500">{sectionId}</p>
        <h2 className="mt-2 text-2xl font-semibold tracking-tight text-zinc-100 sm:mt-2.5 sm:text-3xl md:text-4xl">
          {resolvedTitle}
        </h2>
        {note ? (
          <p className="mt-2 max-w-3xl text-xs leading-relaxed text-zinc-500 sm:mt-3">{note}</p>
        ) : null}
        {lead ? (
          <div className="mt-10 md:mt-12">
            <EmphasisLead text={lead} />
          </div>
        ) : null}
      </div>
    </FadeInView>
  );
}

export function SectionShell({
  sectionId,
  title,
  lead,
  children,
}: {
  sectionId: string;
  title: string;
  lead?: string;
  children: ReactNode;
}) {
  return (
    <div className="competitor-section relative w-full">
      <SectionHeader sectionId={sectionId} title={title} lead={lead} />
      <div className="mt-5 flex flex-col gap-5 sm:mt-6 sm:gap-6">{children}</div>
    </div>
  );
}
