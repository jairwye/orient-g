"use client";

import type { CompetitorEdition } from "../lib/types";
import { EditionSwitcher } from "./EditionSwitcher";
import { ProgressScale } from "./ProgressScale";

type Props = {
  activeSnapId: string;
  onNavigate: (id: string) => void;
  periodLabel?: string | null;
  editions?: CompetitorEdition[];
  activeEditionId?: string | null;
  currentEditionId?: string | null;
};

/** 页顶：标题旁 Ghost 期次切换（shrink-0）；右侧 ProgressScale 占剩余宽度 */
export function CompetitorPageHeader({
  activeSnapId,
  onNavigate,
  periodLabel,
  editions = [],
  activeEditionId = null,
  currentEditionId = null,
}: Props) {
  const showSwitcher = editions.length > 1;

  return (
    <div className="competitor-page-header relative z-30 shrink-0 px-6 pb-3 pt-6 md:px-8 md:pt-8">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
        <div className="flex shrink-0 items-baseline gap-3">
          <h1 className="shrink-0 text-2xl font-semibold tracking-tight text-zinc-100">
            竞品财报
          </h1>
          {showSwitcher ? (
            <EditionSwitcher
              editions={editions}
              activeEditionId={activeEditionId}
              currentEditionId={currentEditionId}
            />
          ) : periodLabel ? (
            <span
              className="truncate text-sm font-medium text-zinc-400"
              title={periodLabel}
            >
              {periodLabel}
            </span>
          ) : null}
        </div>
        <ProgressScale activeSnapId={activeSnapId} onNavigate={onNavigate} />
      </div>
    </div>
  );
}
