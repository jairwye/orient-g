"use client";

import Link from "next/link";
import { competitorReportHref } from "../lib/navigation";
import { VerticalProgressScale } from "./VerticalProgressScale";
import type { VerticalReportSnapshot } from "../lib/vertical_types";
import type { CompetitorReportSnapshot } from "../lib/types";

type Props = {
  report: VerticalReportSnapshot | null;
  competitorSnapshot?: CompetitorReportSnapshot | null;
  activeSnapId: string;
  onNavigate: (id: string) => void;
};

/** 纵向对比页顶：标题 + 公司刻度（数据来自 API） */
export function VerticalPageHeader({ report, competitorSnapshot, activeSnapId, onNavigate }: Props) {
  return (
    <div className="competitor-page-header shrink-0 px-6 pb-3 pt-6 md:px-8 md:pt-8">
      <div className="flex items-center justify-between gap-4">
        <div className="flex min-w-0 shrink-0 items-center gap-3">
          <h1 className="shrink-0 text-2xl font-semibold tracking-tight text-zinc-100">纵向对比</h1>
          <Link
            href={competitorReportHref()}
            className="hidden shrink-0 rounded-md border border-zinc-700/80 px-2.5 py-1 text-xs text-zinc-400 transition hover:border-zinc-500 hover:text-zinc-200 sm:inline-block"
          >
            返回竞品财报
          </Link>
        </div>
        {report ? (
          <VerticalProgressScale
            report={report}
            competitorSnapshot={competitorSnapshot ?? undefined}
            activeSnapId={activeSnapId}
            onNavigate={onNavigate}
          />
        ) : null}
      </div>
    </div>
  );
}
