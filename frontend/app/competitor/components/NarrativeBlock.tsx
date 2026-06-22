"use client";

import { useMemo } from "react";
import type { NarrativeBlock } from "../lib/types";
import type { CompetitorReportSnapshot } from "../lib/types";
import { formatNarrative, narrativeLeadExcerpt } from "../lib/narrative_format";
import { companyLabelsForSnapshot } from "../lib/companies";
import { FadeInView } from "./FadeInView";

function isMeaningful(markdown: string): boolean {
  const t = markdown.trim();
  return t.length > 2 && t !== "---";
}

function renderSectionTitle(title: string) {
  const dash = title.match(/^(.+?)——(.+)$/);
  if (!dash) return title;
  return (
    <>
      <span className="text-zinc-300">{dash[1]}</span>
      <span className="mx-1 text-zinc-600">——</span>
      <span className="text-zinc-200">{dash[2]}</span>
    </>
  );
}

function renderInlineBold(text: string) {
  const bits = text.split(/(\*\*[^*]+\*\*)/g);
  return bits.map((bit, i) => {
    const bold = bit.match(/^\*\*([^*]+)\*\*$/);
    if (bold) {
      return (
        <strong key={i} className="font-medium text-zinc-300">
          {bold[1]}
        </strong>
      );
    }
    return <span key={i}>{bit}</span>;
  });
}

function renderPlainParagraph(text: string, snapshot?: CompetitorReportSnapshot) {
  for (const label of companyLabelsForSnapshot(snapshot)) {
    if (text.startsWith(label)) {
      const rest = text.slice(label.length).replace(/^[，,：:\s]+/, "");
      return (
        <>
          <span className="font-medium text-zinc-300">{label}</span>
          {rest ? renderInlineBold(`，${rest}`) : null}
        </>
      );
    }
  }
  return renderInlineBold(text);
}

/** 开篇强调段落（无引号装饰） */
export function EmphasisLead({ text, delayMs = 0, className = "" }: { text: string; delayMs?: number; className?: string }) {
  const trimmed = text.trim();
  if (!trimmed) return null;

  return (
    <FadeInView delayMs={delayMs}>
      <p
        className={
          "max-w-4xl border-l-2 border-blue-600/55 pl-4 text-base font-medium leading-relaxed text-zinc-200 sm:pl-5 sm:text-lg sm:leading-relaxed " +
          className
        }
      >
        {renderInlineBold(trimmed)}
      </p>
    </FadeInView>
  );
}

/** @deprecated 使用 EmphasisLead */
export function QuotedLead({ text, delayMs = 0, className = "" }: { text: string; delayMs?: number; className?: string }) {
  return <EmphasisLead text={text} delayMs={delayMs} className={className} />;
}

export function FormattedNarrativeBody({
  markdown,
  delayMs = 0,
  immediate = false,
  columns = false,
  plain = false,
  stripAnalysisPrefix = false,
  snapshot,
}: {
  markdown: string;
  delayMs?: number;
  immediate?: boolean;
  columns?: boolean;
  /** 无强调框/公司卡片，连续正文 */
  plain?: boolean;
  /** 隐藏「分析——」小标题，正文按主体拆行 */
  stripAnalysisPrefix?: boolean;
  snapshot?: CompetitorReportSnapshot;
}) {
  const parts = useMemo(
    () => formatNarrative(markdown, { splitCompanies: !plain, stripAnalysisPrefix, snapshot }),
    [markdown, plain, stripAnalysisPrefix, snapshot],
  );
  if (!parts.length) return null;

  return (
    <FadeInView delayMs={delayMs} immediate={immediate}>
      <div className={columns ? "grid gap-3 sm:gap-4 lg:grid-cols-3" : "space-y-3 sm:space-y-4"}>
        {parts.map((part, i) => {
          if (part.kind === "section") {
            return (
              <div
                key={i}
                className={
                  columns
                    ? "flex flex-col rounded-md border border-zinc-800/70 bg-zinc-950/50 p-3 sm:p-3.5"
                    : "space-y-2"
                }
              >
                <h4 className="text-sm font-medium leading-snug text-zinc-200">{renderSectionTitle(part.title)}</h4>
                {part.body ? (
                  <p className="mt-1.5 text-sm leading-relaxed text-zinc-400">{renderInlineBold(part.body)}</p>
                ) : null}
              </div>
            );
          }
          if (part.kind === "company") {
            if (plain) {
              return (
                <p key={i} className="text-sm leading-relaxed text-zinc-400">
                  <span className="font-medium text-zinc-300">{part.company}</span>
                  {renderInlineBold(part.text.startsWith("，") || part.text.startsWith(",") ? part.text : `，${part.text}`)}
                </p>
              );
            }
            return (
              <div
                key={i}
                className="rounded-lg border border-zinc-800/70 bg-zinc-900/35 px-4 py-3 sm:px-5 sm:py-3.5"
              >
                <p className="text-xs font-medium tracking-wide text-blue-200/90">{part.company}</p>
                <p className="mt-1.5 text-sm leading-relaxed text-zinc-400">{renderInlineBold(part.text)}</p>
              </div>
            );
          }
          if (part.kind === "list") {
            return (
              <ol
                key={i}
                className={
                  "list-decimal space-y-2 pl-5 text-sm leading-relaxed text-zinc-400 " +
                  (columns ? "lg:col-span-3" : "")
                }
              >
                {part.items.map((item, j) => (
                  <li key={j}>{renderInlineBold(item.replace(/^\(\d+\)\s*/, ""))}</li>
                ))}
              </ol>
            );
          }
          return (
            <p key={i} className="text-sm leading-relaxed text-zinc-400">
              {plain ? renderPlainParagraph(part.text, snapshot) : renderInlineBold(part.text)}
            </p>
          );
        })}
      </div>
    </FadeInView>
  );
}

export function InlineNarrative({
  block,
  delayMs = 0,
  immediate = false,
  columns = false,
  plain = false,
  stripAnalysisPrefix = false,
  snapshot,
}: {
  block: NarrativeBlock;
  delayMs?: number;
  immediate?: boolean;
  columns?: boolean;
  plain?: boolean;
  stripAnalysisPrefix?: boolean;
  snapshot?: CompetitorReportSnapshot;
}) {
  if (!isMeaningful(block.markdown)) return null;
  const body = (
    <FormattedNarrativeBody
      markdown={block.markdown}
      delayMs={delayMs}
      immediate={immediate}
      columns={columns}
      plain={plain}
      stripAnalysisPrefix={stripAnalysisPrefix}
      snapshot={snapshot}
    />
  );
  if (plain) return body;
  return <div className="border-l-2 border-blue-600/50 pl-4 md:pl-5">{body}</div>;
}

export function NarrativesFromSection({
  blocks,
  inline = true,
  anchor,
  anchors,
  immediate = false,
  columns = false,
  plain = false,
  stripAnalysisPrefix = false,
  snapshot,
}: {
  blocks: Array<{ kind: string; markdown?: string; anchor?: string }>;
  inline?: boolean;
  /** 仅渲染指定锚点的叙事 */
  anchor?: string;
  /** 渲染多个锚点（按 blocks 顺序） */
  anchors?: string[];
  immediate?: boolean;
  columns?: boolean;
  plain?: boolean;
  stripAnalysisPrefix?: boolean;
  snapshot?: CompetitorReportSnapshot;
}) {
  let narratives = blocks.filter(
    (b) => b.kind === "narrative" && b.markdown && isMeaningful(b.markdown),
  ) as NarrativeBlock[];

  if (anchor) {
    narratives = narratives.filter((b) => b.anchor === anchor);
  } else if (anchors?.length) {
    const order = new Map(anchors.map((a, i) => [a, i]));
    narratives = narratives
      .filter((b) => b.anchor && order.has(b.anchor))
      .sort((a, b) => (order.get(a.anchor!) ?? 0) - (order.get(b.anchor!) ?? 0));
  }

  if (!narratives.length) return null;

  if (inline) {
    return (
      <div className="space-y-5 sm:space-y-6">
        {narratives.map((b, i) => (
          <InlineNarrative
            key={b.anchor ?? i}
            block={b}
            delayMs={i * 80}
            immediate={immediate}
            columns={columns}
            plain={plain}
            stripAnalysisPrefix={stripAnalysisPrefix}
            snapshot={snapshot}
          />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {narratives.map((b, i) => (
        <details
          key={b.anchor ?? i}
          className="rounded-lg border border-zinc-800 bg-zinc-900/30 px-4 py-3 text-sm text-zinc-400"
        >
          <summary className="cursor-pointer select-none text-zinc-300">分析摘要</summary>
          <div className="mt-3">
            <FormattedNarrativeBody markdown={b.markdown} />
          </div>
        </details>
      ))}
    </div>
  );
}

export function firstNarrativeLead(blocks: Array<{ kind: string; markdown?: string }>): string | undefined {
  const hit = blocks.find(
    (b) => b.kind === "narrative" && b.markdown && isMeaningful(b.markdown),
  ) as NarrativeBlock | undefined;
  if (!hit) return undefined;
  return narrativeLeadExcerpt(hit.markdown);
}
