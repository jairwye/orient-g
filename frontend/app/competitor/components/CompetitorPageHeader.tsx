"use client";

import { ProgressScale } from "./ProgressScale";

type Props = {
  activeSnapId: string;
  onNavigate: (id: string) => void;
};

/** 页顶标题 + 横向章节刻度（靠右） */
export function CompetitorPageHeader({ activeSnapId, onNavigate }: Props) {
  return (
    <div className="competitor-page-header shrink-0 px-6 pb-3 pt-6 md:px-8 md:pt-8">
      <div className="flex items-center justify-between gap-4">
        <h1 className="shrink-0 text-2xl font-semibold tracking-tight text-zinc-100">竞品财报</h1>
        <ProgressScale activeSnapId={activeSnapId} onNavigate={onNavigate} />
      </div>
    </div>
  );
}
