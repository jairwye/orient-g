"use client";

import { DataTable } from "./DataTable";
import { FormattedNarrativeBody } from "./NarrativeBlock";
import { FadeInView } from "./FadeInView";
import type { VerticalReportBlock } from "../lib/vertical_types";

function renderSectionTitle(title: string) {
  const dash = title.match(/^(.+?[、．.][^—-]*?)[—-](.+)$/);
  if (!dash) return title;
  return (
    <>
      <span>{dash[1]}</span>
      <span className="mx-1.5 font-normal text-zinc-600">—</span>
      <span className="font-normal text-zinc-300">{dash[2]}</span>
    </>
  );
}

export function VerticalReportBody({ blocks }: { blocks: VerticalReportBlock[] }) {
  if (!blocks.length) return null;

  return (
    <div className="w-full space-y-5 sm:space-y-6">
      {blocks.map((block, i) => {
        if (block.kind === "table" && block.headers?.length) {
          return (
            <FadeInView key={i} className="w-full" delayMs={Math.min(i * 40, 200)}>
              <DataTable
                headers={block.headers}
                headerKeys={block.header_keys}
                rows={block.rows}
                compact
                wrapText
                flowContent
                delayMs={0}
              />
            </FadeInView>
          );
        }
        if (block.kind === "narrative" && block.markdown?.trim()) {
          return (
            <FadeInView key={i} className="w-full" delayMs={Math.min(i * 40, 200)}>
              <FormattedNarrativeBody markdown={block.markdown} plain delayMs={0} immediate />
            </FadeInView>
          );
        }
        return null;
      })}
    </div>
  );
}

export function VerticalInternalSection({
  id,
  title,
  blocks,
  index,
}: {
  id: string;
  title: string;
  blocks: VerticalReportBlock[];
  index: number;
}) {
  if (!blocks.length) return null;

  const isFirst = index === 0;

  return (
    <section
      id={id}
      className={
        (isFirst ? "pt-2" : "mt-12 border-t border-zinc-800/90 pt-10 sm:mt-14 sm:pt-12") +
        " scroll-mt-28"
      }
    >
      {title && title !== "正文" ? (
        <header className="mb-6 sm:mb-8">
          <h3 className="text-base font-semibold leading-snug tracking-tight text-zinc-100 sm:text-lg">
            {renderSectionTitle(title)}
          </h3>
        </header>
      ) : null}
      <VerticalReportBody blocks={blocks} />
    </section>
  );
}
