"use client";

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useAuth } from "../../contexts/AuthContext";
import { competitorReportHref } from "../lib/navigation";
import { VerticalPageHeader } from "../components/VerticalPageHeader";
import { VerticalPdfViewer } from "../components/VerticalPdfViewer";
import { VerticalInternalSection } from "../components/VerticalReportBody";
import { VerticalPreservedText } from "../components/VerticalPreservedText";
import { SnapContent, SnapPanel } from "../components/SnapPanel";
import { useSnapScrollObserver } from "../components/ProgressScale";
import { colorForCompany } from "../lib/competitor_chart_colors";
import { runtimeCompanyDisplayName } from "../lib/companies";
import { allVerticalSnapIds, type VerticalCompanyNav } from "../lib/vertical_navigation";
import type { CompetitorReportSnapshot } from "../lib/types";
import { useCompetitorReport } from "../lib/useCompetitorReport";
import { useVerticalPdfMeta } from "../lib/useVerticalPdfMeta";
import { useVerticalReport } from "../lib/useVerticalReport";
import { CompetitorScrollProvider } from "../lib/scroll_context";

function VerticalCompareEmptyState({ financePath }: { financePath: string }) {
  return (
    <div className="competitor-canvas flex min-h-[60vh] flex-col p-6 md:p-8">
      <h1 className="text-2xl font-semibold tracking-tight text-zinc-100">纵向对比</h1>
      <div className="flex flex-1 flex-col items-center justify-center gap-4 text-center">
        <p className="max-w-md text-sm text-zinc-500">
          暂无纵向分析内容。请管理员在财务后台上传 PDF zip（Docling 解析或「仅存档 PDF」），或上传修正后的
          Markdown。
        </p>
        <Link
          href={financePath || "/finance"}
          className="rounded-md border border-zinc-600 bg-zinc-800 px-4 py-2 text-sm text-zinc-200 hover:bg-zinc-700"
        >
          前往财务后台上传
        </Link>
        <Link
          href={competitorReportHref()}
          className="rounded-md border border-zinc-600 bg-zinc-800 px-4 py-2 text-sm text-zinc-200 hover:bg-zinc-700"
        >
          返回竞品财报
        </Link>
      </div>
    </div>
  );
}

function VerticalPdfModeView({
  pdfNavCompanies,
  competitorSnapshot,
  activeSnapId,
  navigate,
}: {
  pdfNavCompanies: VerticalCompanyNav[];
  competitorSnapshot?: CompetitorReportSnapshot;
  activeSnapId: string;
  navigate: (snapId: string) => void;
}) {
  const activePdfCompany = pdfNavCompanies.find((c) => c.snapId === activeSnapId);

  return (
    <CompetitorScrollProvider jumpToSnap={navigate} activeSnapId={activeSnapId}>
      <div className="competitor-canvas absolute inset-0 flex flex-col overflow-hidden">
        <VerticalPageHeader
          navCompanies={pdfNavCompanies}
          competitorSnapshot={competitorSnapshot}
          activeSnapId={activeSnapId}
          onNavigate={navigate}
        />
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden" data-testid="vertical-pdf-root">
          {activePdfCompany ? (
            <VerticalPdfViewer key={activePdfCompany.id} companyId={activePdfCompany.id} fullscreen />
          ) : (
            <div className="flex flex-1 items-center justify-center text-sm text-zinc-500">请在上方选择公司</div>
          )}
        </div>
      </div>
    </CompetitorScrollProvider>
  );
}

function VerticalSnapshotModeView({
  competitorSnapshot,
  financePath,
}: {
  competitorSnapshot?: CompetitorReportSnapshot;
  financePath: string;
}) {
  const { state, reload } = useVerticalReport();
  const scrollRef = useRef<HTMLDivElement>(null);
  const scrollReady = state.status === "ready";
  const readyData = state.status === "ready" ? state.data : null;
  const snapIds = useMemo(
    () => (readyData ? allVerticalSnapIds(readyData) : []),
    [readyData],
  );
  const { activeSnapId, navigate } = useSnapScrollObserver(snapIds, scrollRef, scrollReady);

  useEffect(() => {
    if (state.status !== "ready") return;
    const hash = typeof window !== "undefined" ? window.location.hash.replace(/^#/, "") : "";
    if (hash && snapIds.includes(hash)) {
      const t = window.setTimeout(() => navigate(hash), 80);
      return () => window.clearTimeout(t);
    }
  }, [state.status, navigate, snapIds]);

  if (state.status === "loading") {
    return (
      <div className="competitor-canvas p-6 md:p-8">
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-100">纵向对比</h1>
        <div className="mt-8 flex min-h-[40vh] items-center justify-center">
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 px-8 py-6 text-sm text-zinc-500">
            加载纵向分析报告…
          </div>
        </div>
      </div>
    );
  }

  if (state.status === "empty") {
    return <VerticalCompareEmptyState financePath={financePath} />;
  }

  if (state.status === "error") {
    return (
      <div className="competitor-canvas flex min-h-[60vh] flex-col p-6 md:p-8">
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-100">纵向对比</h1>
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

  const { data } = state;
  const introNarratives = (data.intro ?? []).filter((b) => b.kind === "narrative");

  return (
    <CompetitorScrollProvider jumpToSnap={navigate} activeSnapId={activeSnapId}>
      <div className="competitor-canvas absolute inset-0 flex flex-col overflow-hidden">
        <VerticalPageHeader
          report={data}
          competitorSnapshot={competitorSnapshot}
          activeSnapId={activeSnapId}
          onNavigate={navigate}
        />
        <div
          ref={scrollRef}
          className="competitor-scroll min-h-0 flex-1 overflow-y-auto"
          data-testid="vertical-scroll-root"
        >
          {introNarratives.length > 0 ? (
            <SnapPanel id="v-intro" dense>
              <SnapContent className="py-8 sm:py-10">
                <div className="w-full space-y-6">
                  {introNarratives.map((b, i) =>
                    b.kind === "narrative" ? (
                      <VerticalPreservedText key={i} markdown={b.markdown} />
                    ) : null,
                  )}
                </div>
              </SnapContent>
            </SnapPanel>
          ) : null}

          {data.companies.map((company, index) => {
            const accent = colorForCompany(company.id);
            const sections =
              company.sections?.length > 0
                ? company.sections
                : [{ id: company.snap_id, title: "", blocks: company.blocks }];
            return (
              <SnapPanel key={company.snap_id} id={company.snap_id} dense>
                <SnapContent className="py-8 sm:py-10">
                  <div className="w-full">
                    <div className="border-t-[3px] pt-6 sm:pt-8" style={{ borderTopColor: accent }}>
                      <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-zinc-500">
                        {String(index + 1).padStart(2, "0")} / {data.companies.length}
                      </p>
                      <h2 className="mt-2 text-2xl font-semibold tracking-tight text-zinc-100 sm:text-3xl md:text-4xl">
                        {runtimeCompanyDisplayName(company.id, competitorSnapshot, company.name)}
                      </h2>
                    </div>
                    <div className="mt-8 sm:mt-10">
                      <div className="space-y-2">
                        {sections.map((section, secIndex) => (
                          <VerticalInternalSection
                            key={section.id}
                            id={section.id}
                            title={section.title}
                            blocks={section.blocks}
                            index={secIndex}
                          />
                        ))}
                      </div>
                    </div>
                  </div>
                </SnapContent>
              </SnapPanel>
            );
          })}
        </div>
      </div>
    </CompetitorScrollProvider>
  );
}

function VerticalComparePageInner() {
  const { finance_path } = useAuth();
  const { state: pdfMetaState } = useVerticalPdfMeta();
  const { state: competitorState } = useCompetitorReport();
  const competitorSnapshot = competitorState.status === "ready" ? competitorState.data : undefined;

  const usePdfMode = pdfMetaState.status === "ready";

  const pdfNavCompanies: VerticalCompanyNav[] = useMemo(() => {
    if (pdfMetaState.status !== "ready") return [];
    return (pdfMetaState.data.companies ?? []).map((c) => ({
      id: c.id,
      snapId: `v-${c.id}`,
      name: runtimeCompanyDisplayName(c.id, competitorSnapshot, c.name),
    }));
  }, [pdfMetaState, competitorSnapshot]);

  const pdfSnapIds = useMemo(() => pdfNavCompanies.map((c) => c.snapId), [pdfNavCompanies]);
  const [activeSnapId, setActiveSnapId] = useState("");

  const resolveInitialPdfSnap = useCallback((ids: string[]) => {
    if (!ids.length) return "";
    const hash = typeof window !== "undefined" ? window.location.hash.replace(/^#/, "") : "";
    if (hash && ids.includes(hash)) return hash;
    return ids[0];
  }, []);

  useEffect(() => {
    if (!usePdfMode || !pdfSnapIds.length) return;
    setActiveSnapId((prev) => {
      if (prev && pdfSnapIds.includes(prev)) return prev;
      return resolveInitialPdfSnap(pdfSnapIds);
    });
  }, [usePdfMode, pdfSnapIds, resolveInitialPdfSnap]);

  useEffect(() => {
    if (!usePdfMode || !activeSnapId) return;
    const hash = window.location.hash.replace(/^#/, "");
    if (hash !== activeSnapId) {
      window.history.replaceState(null, "", `#${activeSnapId}`);
    }
  }, [usePdfMode, activeSnapId]);

  const navigatePdf = useCallback((snapId: string) => {
    setActiveSnapId(snapId);
    window.history.replaceState(null, "", `#${snapId}`);
  }, []);

  if (pdfMetaState.status === "loading") {
    return (
      <div className="competitor-canvas p-6 md:p-8">
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-100">纵向对比</h1>
        <div className="mt-8 flex min-h-[40vh] items-center justify-center">
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 px-8 py-6 text-sm text-zinc-500">
            加载纵向分析…
          </div>
        </div>
      </div>
    );
  }

  if (usePdfMode) {
    return (
      <VerticalPdfModeView
        pdfNavCompanies={pdfNavCompanies}
        competitorSnapshot={competitorSnapshot}
        activeSnapId={activeSnapId}
        navigate={navigatePdf}
      />
    );
  }

  if (pdfMetaState.status === "error") {
    return (
      <VerticalSnapshotModeView
        competitorSnapshot={competitorSnapshot}
        financePath={finance_path || "/finance"}
      />
    );
  }

  return (
    <VerticalSnapshotModeView
      competitorSnapshot={competitorSnapshot}
      financePath={finance_path || "/finance"}
    />
  );
}

export default function VerticalComparePage() {
  return (
    <Suspense
      fallback={
        <div className="competitor-canvas p-6 md:p-8">
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-100">纵向对比</h1>
          <div className="mt-8 text-sm text-zinc-500">加载中…</div>
        </div>
      }
    >
      <VerticalComparePageInner />
    </Suspense>
  );
}
