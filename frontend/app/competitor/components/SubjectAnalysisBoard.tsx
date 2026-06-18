"use client";

import { colorForCompany } from "../lib/competitor_chart_colors";
import type { SubjectAnalysisGroup } from "../lib/balance_subject_analysis";
import type { InsightTone } from "../lib/finance_analysis";
import { CL } from "../lib/field_keys";
import type { CompetitorReportSnapshot } from "../lib/types";
import { FadeInView } from "./FadeInView";

const TONE_DOT: Record<InsightTone, string> = {
  positive: "bg-emerald-400",
  warning: "bg-amber-400",
  negative: "bg-red-400",
  neutral: "bg-blue-400",
};

type Props = {
  groups: SubjectAnalysisGroup[];
  snapshot: CompetitorReportSnapshot;
  delayMs?: number;
  /** company=分主体（公司色条）；topic=分主题（统一 zinc 强调） */
  mode?: "company" | "topic";
};

export function SubjectAnalysisBoard({ groups, snapshot, delayMs = 200, mode = "company" }: Props) {
  if (!groups.length) return null;

  const heading = mode === "topic" ? CL.topicAnalysis : CL.subjectAnalysis;

  return (
    <FadeInView delayMs={delayMs}>
      <div className="mt-6 space-y-4 border-t border-zinc-800/80 pt-5 sm:mt-8 sm:space-y-5 sm:pt-6">
        <p className="text-xs font-medium tracking-wide text-zinc-500">{heading}</p>
        <div className="grid gap-3 sm:grid-cols-2 xl:gap-4">
          {groups.map((group, gi) => {
            const accent =
              mode === "topic" || !group.colKey
                ? "#52525b"
                : colorForCompany(group.colKey, snapshot);
            return (
              <article
                key={group.company}
                className="rounded-lg border border-zinc-800/80 bg-zinc-900/35 p-3.5 sm:p-4"
                style={{ borderLeftWidth: 3, borderLeftColor: accent }}
              >
                <header className="mb-2.5 flex items-center gap-2">
                  <span
                    className="inline-block h-2 w-2 shrink-0 rounded-full"
                    style={{ backgroundColor: accent }}
                    aria-hidden
                  />
                  <h3 className="text-sm font-medium text-zinc-100">{group.company}</h3>
                </header>
                <ul className="space-y-2">
                  {group.bullets.map((bullet, bi) => (
                    <li key={`${gi}-${bi}`} className="flex gap-2 text-xs leading-relaxed sm:text-[13px]">
                      {bullet.tone ? (
                        <span
                          className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${TONE_DOT[bullet.tone]}`}
                          aria-hidden
                        />
                      ) : (
                        <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-zinc-600" aria-hidden />
                      )}
                      <div className="min-w-0 flex-1">
                        {bullet.tag ? (
                          <span className="mr-1.5 inline-block rounded bg-zinc-800/80 px-1 py-px text-[10px] text-zinc-500">
                            {bullet.tag}
                          </span>
                        ) : null}
                        <span className="text-zinc-300">{bullet.text}</span>
                      </div>
                    </li>
                  ))}
                </ul>
              </article>
            );
          })}
        </div>
      </div>
    </FadeInView>
  );
}
