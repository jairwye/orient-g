"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useRef } from "react";
import { useAuth } from "../contexts/AuthContext";
import { CompetitorPageHeader } from "./components/CompetitorPageHeader";
import { CompetitorWarningsBanner } from "./components/CompetitorWarningsBanner";
import { useSnapScrollObserver } from "./components/ProgressScale";
import { ALL_SNAP_IDS } from "./lib/navigation";
import { CompetitorScrollProvider } from "./lib/scroll_context";
import { useCompetitorReport } from "./lib/useCompetitorReport";
import type { SectionProps } from "./lib/section_ui";
import { Sec01Overview } from "./sections/Sec01Overview";
import { Sec02Ranking } from "./sections/Sec02Ranking";
import { Sec03Operating } from "./sections/Sec03Operating";

const Sec04People = dynamic(
  () => import("./sections/Sec04People").then((m) => ({ default: m.Sec04People })),
  { ssr: false },
);
const Sec05Revenue = dynamic(
  () => import("./sections/Sec05Revenue").then((m) => ({ default: m.Sec05Revenue })),
  { ssr: false },
);
const Sec05Region = dynamic(
  () => import("./sections/Sec05Region").then((m) => ({ default: m.Sec05Region })),
  { ssr: false },
);
const Sec06Balance = dynamic(
  () => import("./sections/Sec06Balance").then((m) => ({ default: m.Sec06Balance })),
  { ssr: false },
);
const Sec07Profit = dynamic(
  () => import("./sections/Sec07Profit").then((m) => ({ default: m.Sec07Profit })),
  { ssr: false },
);
const Sec08Cashflow = dynamic(
  () => import("./sections/Sec08Cashflow").then((m) => ({ default: m.Sec08Cashflow })),
  { ssr: false },
);
const Sec09Others = dynamic(
  () => import("./sections/Sec09Others").then((m) => ({ default: m.Sec09Others })),
  { ssr: false },
);
const Sec10Risk = dynamic(
  () => import("./sections/Sec10Risk").then((m) => ({ default: m.Sec10Risk })),
  { ssr: false },
);

export default function CompetitorPage() {
  const { finance_path } = useAuth();
  const { state, reload } = useCompetitorReport();
  const scrollRef = useRef<HTMLDivElement>(null);
  const scrollReady = state.status === "ready";
  const { activeSnapId, navigate } = useSnapScrollObserver(ALL_SNAP_IDS, scrollRef, scrollReady);

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
    return (
      <div className="competitor-canvas flex min-h-[60vh] flex-col p-6 md:p-8">
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-100">竞品财报</h1>
        <div className="flex flex-1 flex-col items-center justify-center gap-4 text-center">
          <p className="max-w-md text-sm text-zinc-500">
            请在财务后台上传 Markdown 蓝本（须含 sec-01～sec-10 锚点）。
          </p>
          <Link
            href={finance_path || "/finance"}
            className="rounded-md border border-zinc-600 bg-zinc-800 px-4 py-2 text-sm text-zinc-200 hover:bg-zinc-700"
          >
            前往财务后台上传
          </Link>
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
          <button
            type="button"
            onClick={() => reload()}
            className="rounded-md border border-zinc-600 px-3 py-1.5 text-sm text-zinc-300 hover:bg-zinc-800"
          >
            重试
          </button>
        </div>
      </div>
    );
  }

  const sectionProps: SectionProps = { snapshot: state.data };
  const isFixture = state.data.meta?.data_source === "fixture";
  const warnings = state.data.warnings ?? [];

  return (
    <CompetitorScrollProvider jumpToSnap={navigate}>
      <div className="competitor-canvas absolute inset-0 flex flex-col overflow-hidden">
        <CompetitorPageHeader activeSnapId={activeSnapId} onNavigate={navigate} />
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
            <Sec10Risk {...sectionProps} />
        </div>
      </div>
    </CompetitorScrollProvider>
  );
}
