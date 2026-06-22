"use client";

import Link from "next/link";
import { ChapterPanel } from "../components/ChapterPanel";
import { FadeInView } from "../components/FadeInView";
import { colorForCompany } from "../lib/competitor_chart_colors";
import type { SectionProps } from "../lib/section_ui";
import { useVerticalReport } from "../lib/useVerticalReport";
import { verticalCompaniesForDisplay, verticalReportHref } from "../lib/vertical_navigation";

export function Sec10DetailLinks({ snapshot }: SectionProps) {
  const { state } = useVerticalReport();
  const companies =
    state.status === "ready" ? verticalCompaniesForDisplay(state.data, snapshot) : [];

  return (
    <ChapterPanel
      sectionId="sec-10"
      slides={[
        {
          id: "sec-10-a",
          title: "详情链接",
          content: (
            <div className="mx-auto max-w-3xl space-y-6">
              <p className="text-sm leading-relaxed text-zinc-400">
                以下链接跳转至「纵向对比」页，查看各竞品公司 2025 年度纵向分析全文。
              </p>
              {state.status === "loading" ? (
                <p className="text-sm text-zinc-500">加载纵向分析目录…</p>
              ) : companies.length === 0 ? (
                <p className="text-sm text-zinc-500">
                  暂无纵向分析报告。请将 MD 置于 uploads/competitor/vertical_report.md 后刷新。
                </p>
              ) : (
                <ul className="grid gap-3 sm:grid-cols-2">
                  {companies.map((co, i) => {
                    const accent = colorForCompany(co.id, snapshot);
                    return (
                      <FadeInView key={co.snapId} delayMs={i * 50}>
                        <li>
                          <Link
                            href={verticalReportHref(co.snapId)}
                            className="group flex items-center gap-3 rounded-lg border border-zinc-800 bg-zinc-900/50 px-4 py-3.5 transition hover:border-zinc-600 hover:bg-zinc-900/80"
                            style={{ borderLeftColor: accent, borderLeftWidth: 3 }}
                          >
                            <span
                              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-xs font-semibold text-zinc-950"
                              style={{ backgroundColor: accent }}
                            >
                              {co.name.slice(0, 1)}
                            </span>
                            <span className="min-w-0 flex-1">
                              <span className="block text-sm font-medium text-zinc-100 group-hover:text-blue-200">
                                {co.name}
                              </span>
                              <span className="mt-0.5 block text-xs text-zinc-500">纵向对比 · 2025 年报分析</span>
                            </span>
                            <span className="shrink-0 text-zinc-600 transition group-hover:text-blue-400" aria-hidden>
                              →
                            </span>
                          </Link>
                        </li>
                      </FadeInView>
                    );
                  })}
                </ul>
              )}
            </div>
          ),
        },
      ]}
    />
  );
}
