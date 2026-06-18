"use client";

import { colorForCompany } from "../lib/competitor_chart_colors";
import type { TopicSubjectGroup } from "../lib/sec09_topic_subject_analysis";
import { CL } from "../lib/field_keys";
import type { CompetitorReportSnapshot } from "../lib/types";
import { BUSINESS_CHART_COLORS } from "../../lib/business_chart_colors";
import { FadeInView } from "./FadeInView";

type Props = {
  groups: TopicSubjectGroup[];
  snapshot: CompetitorReportSnapshot;
  delayMs?: number;
};

/** 分主题解读：与 TopicAnalysisBoard 一致的 2 列卡片 + 左侧主题蓝条，卡片内按主体分行 */
export function TopicSubjectBoard({ groups, snapshot, delayMs = 200 }: Props) {
  if (!groups.length) return null;

  return (
    <FadeInView delayMs={delayMs}>
      <div className="mt-6 space-y-4 border-t border-zinc-800/80 pt-5 sm:mt-8 sm:space-y-5 sm:pt-6">
        <p className="text-xs font-medium tracking-wide text-zinc-500">{CL.topicAnalysis}</p>
        <div className="grid gap-3 lg:grid-cols-2 xl:gap-4">
          {groups.map((group) => (
            <article
              key={group.topic}
              className="rounded-lg border border-zinc-800/80 bg-zinc-900/35 p-3.5 sm:p-4"
              style={{ borderLeftWidth: 3, borderLeftColor: BUSINESS_CHART_COLORS.current }}
            >
              <header className="mb-2.5">
                <h3 className="text-sm font-medium leading-snug text-zinc-100">{group.topic}</h3>
              </header>
              <ul className="space-y-2.5">
                {group.subjects.map((sub) => {
                  const accent = sub.colKey ? colorForCompany(sub.colKey, snapshot) : "#52525b";
                  return (
                    <li key={`${group.topic}-${sub.company}`} className="flex gap-2 text-xs leading-relaxed sm:text-[13px]">
                      <span
                        className="mt-1.5 inline-block h-2 w-2 shrink-0 rounded-full"
                        style={{ backgroundColor: accent }}
                        aria-hidden
                      />
                      <div className="min-w-0 flex-1">
                        <span className="mr-1.5 font-medium text-zinc-200">{sub.company}</span>
                        {sub.bullets.map((bullet, bi) => (
                          <span key={bi} className="text-zinc-400">
                            {bi > 0 ? " " : ""}
                            {bullet.text}
                          </span>
                        ))}
                      </div>
                    </li>
                  );
                })}
              </ul>
            </article>
          ))}
        </div>
      </div>
    </FadeInView>
  );
}
