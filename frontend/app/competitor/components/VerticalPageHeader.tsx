"use client";

import Link from "next/link";
import { competitorReportHref } from "../lib/navigation";
import type { VerticalCompanyNav } from "../lib/vertical_navigation";
import type { VerticalReportSnapshot } from "../lib/vertical_types";
import { VerticalProgressScale } from "./VerticalProgressScale";
import type { CompetitorReportSnapshot } from "../lib/types";

type Props = {
  /** Docling/MD snapshot 模式 */
  report?: VerticalReportSnapshot | null;
  /** PDF 直显模式 */
  navCompanies?: VerticalCompanyNav[];
  competitorSnapshot?: CompetitorReportSnapshot | null;
  activeSnapId: string;
  onNavigate: (id: string) => void;
};

/** 纵向对比页顶：标题 + 公司刻度 */
export function VerticalPageHeader({
  report = null,
  navCompanies,
  competitorSnapshot,
  activeSnapId,
  onNavigate,
}: Props) {
  const hasScale = Boolean(report) || Boolean(navCompanies?.length);
  return (
    <div className="competitor-page-header shrink-0 px-6 pb-3 pt-6 md:px-8 md:pt-8">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex min-w-0 shrink-0 flex-wrap items-center gap-3">
          <h1 className="shrink-0 text-2xl font-semibold tracking-tight text-zinc-100">纵向对比</h1>
          <Link
            href={competitorReportHref()}
            className="hidden shrink-0 rounded-md border border-zinc-700/80 px-2.5 py-1 text-xs text-zinc-400 transition hover:border-zinc-500 hover:text-zinc-200 sm:inline-block"
          >
            返回竞品财报
          </Link>
        </div>
        {hasScale ? (
          <VerticalProgressScale
            report={report}
            navCompanies={navCompanies}
            competitorSnapshot={competitorSnapshot ?? undefined}
            activeSnapId={activeSnapId}
            onNavigate={onNavigate}
          />
        ) : null}
      </div>
    </div>
  );
}
