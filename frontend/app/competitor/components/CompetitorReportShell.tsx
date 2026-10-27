"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useRef } from "react";
import { useAuth } from "../../contexts/AuthContext";
import { CompetitorPageHeader } from "./CompetitorPageHeader";
import { CompetitorWarningsBanner } from "./CompetitorWarningsBanner";
import { useSnapScrollObserver } from "./ProgressScale";
import { ALL_SNAP_IDS, competitorHomeHref } from "../lib/navigation";
import { CompetitorScrollProvider } from "../lib/scroll_context";
import { useCompetitorEditions } from "../lib/useCompetitorEditions";
import { useCompetitorReport } from "../lib/useCompetitorReport";
import type { SectionProps } from "../lib/section_ui";
import { Sec01Overview } from "../sections/Sec01Overview";
import { Sec02Ranking } from "../sections/Sec02Ranking";
import { Sec03Operating } from "../sections/Sec03Operating";

const Sec04People = dynamic(
  () => import("../sections/Sec04People").then((m) => ({ default: m.Sec04People })),
  { ssr: false },
);
const Sec05Revenue = dynamic(
  () => import("../sections/Sec05Revenue").then((m) => ({ default: m.Sec05Revenue })),
  { ssr: false },
);
const Sec05Region = dynamic(
  () => import("../sections/Sec05Region").then((m) => ({ default: m.Sec05Region })),
  { ssr: false },
);
const Sec06Balance = dynamic(
  () => import("../sections/Sec06Balance").then((m) => ({ default: m.Sec06Balance })),
  { ssr: false },
);
const Sec07Profit = dynamic(
  () => import("../sections/Sec07Profit").then((m) => ({ default: m.Sec07Profit })),
  { ssr: false },
);
const Sec08Cashflow = dynamic(
  () => import("../sections/Sec08Cashflow").then((m) => ({ default: m.Sec08Cashflow })),
  { ssr: false },
);
const Sec09Others = dynamic(
  () => import("../sections/Sec09Others").then((m) => ({ default: m.Sec09Others })),
  { ssr: false },
);
const Sec10DetailLinks = dynamic(
  () => import("../sections/Sec10DetailLinks").then((m) => ({ default: m.Sec10DetailLinks })),
  { ssr: false },
);

type Props = {
  /** 指定期次；省略则读 current */
  editionId?: string | null;
};

export function CompetitorReportShell({ editionId = null }: Props) {
  const { finance_path } = useAuth();
  const { state, reload } = useCompetitorReport(editionId);
  const { state: editionsState } = useCompetitorEditions();
  const scrollRef = useRef<HTMLDivElement>(null);
  const scrollReady = state.status === "ready";
  const { activeSnapId, navigate } = useSnapScrollObserver(ALL_SNAP_IDS, scrollRef, scrollReady);

  const editions = editionsState.status === "ready" ? editionsState.editions : [];
  const currentEditionId = editionsState.status === "ready" ? editionsState.current : null;
  const activeMeta = editions.find((e) => e.edition_id === (editionId || currentEditionId));
  const periodLabel =
    (state.status === "ready" ? state.data.meta?.period_label : null) ||
    activeMeta?.period_label ||
    null;
  const resolvedEditionId =
    (state.status === "ready" ? state.data.meta?.edition_id : null) || editionId || currentEditionId;
  // 期次元数据未到前：指定深链保守隐藏纵向；current 路由仍可短暂展示入口
  const hasVertical =
    activeMeta == null ? !editionId : Boolean(activeMeta.has_vertical);

  if (state.status === "loading") {
    return (
      <div className="competitor-canvas p-6 md:p-8">
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-100">竞品财报</h1>
        <div className="mt-8 flex min-h-[40vh] items-center justify-center">
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 px-8 py-6 text-sm text-zinc-500">
            加载竞品财报…
          </div>
        </div>
      </div>
    );
  }

  if (state.status === "empty") {
    const knownEdition = Boolean(
      editionId && editions.some((e) => e.edition_id === editionId),
    );
    return (
      <div className="competitor-canvas flex min-h-[60vh] flex-col p-6 md:p-8">
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-100">竞品财报</h1>
        <div className="flex flex-1 flex-col items-center justify-center gap-4 text-center">
          <p className="max-w-md text-sm text-zinc-500">
            {editionId
              ? knownEdition
                ? "该期次尚未上传汇析数据。请管理员在财务后台上传对应 Markdown，或切换其他期次。"
                : "未找到该期次。请返回侧栏默认期次，或在财务后台创建并上传。"
              : "请在财务后台上传 Markdown 蓝本（须含 sec-01～sec-09 锚点），并指定期次。"}
          </p>
          <div className="flex flex-wrap items-center justify-center gap-3">
            {editionId ? (
              <Link
                href={competitorHomeHref()}
                className="rounded-md border border-zinc-600 bg-zinc-800 px-4 py-2 text-sm text-zinc-200 hover:bg-zinc-700"
              >
                返回侧栏默认期次
              </Link>
            ) : null}
            <Link
              href={finance_path || "/finance"}
              className="rounded-md border border-zinc-600 bg-zinc-800 px-4 py-2 text-sm text-zinc-200 hover:bg-zinc-700"
            >
              前往财务后台上传
            </Link>
          </div>
        </div>
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div className="competitor-canvas flex min-h-[60vh] flex-col p-6 md:p-8">
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-100">竞品财报</h1>
        <div className="flex flex-1 flex-col items-center justify-center gap-3">
          <p className="text-sm text-red-400">{state.message}</p>
          <div className="flex flex-wrap items-center justify-center gap-3">
            {editionId ? (
              <Link
                href={competitorHomeHref()}
                className="rounded-md border border-zinc-600 px-3 py-1.5 text-sm text-zinc-300 hover:bg-zinc-800"
              >
                返回侧栏默认期次
              </Link>
            ) : null}
            <button
              type="button"
              onClick={() => reload()}
              className="rounded-md border border-zinc-600 px-3 py-1.5 text-sm text-zinc-300 hover:bg-zinc-800"
            >
              重试
            </button>
          </div>
        </div>
      </div>
    );
  }

  const sectionProps: SectionProps = { snapshot: state.data };
  const isFixture = state.data.meta?.data_source === "fixture";
  const warnings = state.data.warnings ?? [];

  return (
    <CompetitorScrollProvider jumpToSnap={navigate} activeSnapId={activeSnapId}>
      <div className="competitor-canvas absolute inset-0 flex flex-col overflow-hidden">
        <CompetitorPageHeader
          activeSnapId={activeSnapId}
          onNavigate={navigate}
          periodLabel={periodLabel}
          editions={editions}
          activeEditionId={resolvedEditionId}
          currentEditionId={currentEditionId}
        />
        <CompetitorWarningsBanner warnings={warnings} isFixture={isFixture} />
        <div
          ref={scrollRef}
          className="competitor-scroll min-h-0 flex-1 overflow-y-auto"
          data-testid="competitor-scroll-root"
        >
          <Sec01Overview {...sectionProps} />
          <Sec02Ranking {...sectionProps} />
          <Sec03Operating {...sectionProps} />
          <Sec04People {...sectionProps} />
          <Sec05Revenue {...sectionProps} />
          <Sec05Region {...sectionProps} />
          <Sec06Balance {...sectionProps} />
          <Sec07Profit {...sectionProps} />
          <Sec08Cashflow {...sectionProps} />
          <Sec09Others {...sectionProps} />
          {hasVertical ? <Sec10DetailLinks {...sectionProps} /> : null}
        </div>
      </div>
    </CompetitorScrollProvider>
  );
}
