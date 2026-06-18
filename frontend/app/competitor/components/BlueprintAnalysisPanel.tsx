"use client";

import { FormattedNarrativeBody } from "./NarrativeBlock";
import { CL } from "../lib/field_keys";
import { FadeInView } from "./FadeInView";

/** 直接呈现蓝本分析段落，不做分主体切分 */
export function BlueprintAnalysisPanel({ markdown, delayMs = 200 }: { markdown: string; delayMs?: number }) {
  if (!markdown.trim()) return null;

  return (
    <FadeInView delayMs={delayMs}>
      <div className="mt-6 space-y-3 border-t border-zinc-800/80 pt-5 sm:mt-8 sm:pt-6">
        <p className="text-xs font-medium tracking-wide text-zinc-500">{CL.analysisNotes}</p>
        <div className="rounded-lg border border-zinc-800/80 bg-zinc-900/35 p-4 sm:p-5">
          <FormattedNarrativeBody markdown={markdown} plain delayMs={0} immediate />
        </div>
      </div>
    </FadeInView>
  );
}
