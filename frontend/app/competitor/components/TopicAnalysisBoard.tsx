"use client";

import type { TopicAnalysisGroup } from "../lib/topic_analysis";
import type { InsightTone } from "../lib/finance_analysis";
import { CL } from "../lib/field_keys";
import { BUSINESS_CHART_COLORS } from "../../lib/business_chart_colors";
import { FadeInView } from "./FadeInView";

const TONE_DOT: Record<InsightTone, string> = {
  positive: "bg-emerald-400",
  warning: "bg-amber-400",
  negative: "bg-red-400",
  neutral: "bg-blue-400",
};

type Props = {
  groups: TopicAnalysisGroup[];
  delayMs?: number;
};

export function TopicAnalysisBoard({ groups, delayMs = 200 }: Props) {
  if (!groups.length) return null;

  return (
    <FadeInView delayMs={delayMs}>
      <div className="mt-6 space-y-4 border-t border-zinc-800/80 pt-5 sm:mt-8 sm:space-y-5 sm:pt-6">
        <p className="text-xs font-medium tracking-wide text-zinc-500">{CL.topicAnalysis}</p>
        <div className="grid gap-3 lg:grid-cols-2 xl:gap-4">
          {groups.map((group) => (
            <article
              key={group.title}
              className="rounded-lg border border-zinc-800/80 bg-zinc-900/35 p-3.5 sm:p-4"
              style={{ borderLeftWidth: 3, borderLeftColor: BUSINESS_CHART_COLORS.current }}
            >
              <header className="mb-2.5 flex items-start justify-between gap-2">
                <h3 className="text-sm font-medium leading-snug text-zinc-100">{group.displayTitle}</h3>
                <span className="shrink-0 text-[10px] tabular-nums text-zinc-600">{group.bullets.length}</span>
              </header>
              <ul className="space-y-2">
                {group.bullets.map((bullet, bi) => (
                  <li key={bi} className="flex gap-2 text-xs leading-relaxed sm:text-[13px]">
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
          ))}
        </div>
      </div>
    </FadeInView>
  );
}
