"use client";

import type { ReactNode } from "react";
import { SectionHeader } from "../lib/section_ui";
import { SnapContent, SnapPanel } from "./SnapPanel";

export type ChapterSlide = {
  id: string;
  title: string;
  content: ReactNode;
  /** 首屏是否在标题与正文之间加大间距（用于强调段落在 content 内） */
  spacious?: boolean;
  /** 首屏：自顶对齐、略减壳层 padding，提高内容屏占比 */
  hero?: boolean;
  /** 内容密度高：snap 自顶对齐 */
  dense?: boolean;
  /** 子屏：不展示 sec-XX / 章节大标题，仅显示子标题小字 */
  subOnly?: boolean;
};

type Props = {
  sectionId: string;
  lead?: string;
  /** 章节标题下小字（仅首屏 SectionHeader 展示） */
  sectionNote?: string;
  slides: ChapterSlide[];
};

function slideHasContent(content: ReactNode): boolean {
  return content != null && content !== false;
}

export function ChapterPanel({ sectionId, lead, sectionNote, slides }: Props) {
  const visibleSlides = slides.filter((slide) => slideHasContent(slide.content));
  if (!visibleSlides.length) return null;

  return (
    <>
      {visibleSlides.map((slide, index) => (
        <SnapPanel key={slide.id} id={slide.id} dense={slide.dense}>
          <SnapContent
            className={
              "flex min-h-[var(--competitor-viewport-h,100%)] flex-col " +
              (slide.hero ? "justify-start py-4 sm:py-5" : slide.dense ? "justify-start py-6 sm:py-8" : "justify-center py-6 sm:py-8")
            }
          >
            {slide.subOnly ? (
              <div className="shrink-0 pt-6 sm:pt-8">
                <p className="text-xs font-medium text-zinc-500">{slide.title}</p>
              </div>
            ) : index === 0 ? (
              <div className="shrink-0">
                <SectionHeader sectionId={sectionId} lead={lead} note={sectionNote} />
              </div>
            ) : null}
            <div
              className={
                (slide.subOnly
                  ? "mt-4 min-h-0 flex-1 sm:mt-5"
                  : index === 0
                    ? lead
                      ? "mt-6 min-h-0 flex-1 sm:mt-8"
                      : slide.hero
                        ? "mt-8 min-h-0 flex-1 sm:mt-10"
                        : slide.spacious
                          ? "mt-10 min-h-0 flex-1 sm:mt-12"
                          : "mt-6 min-h-0 flex-1 sm:mt-8"
                    : "min-h-0 flex-1") + ""
              }
            >
              {slide.content}
            </div>
          </SnapContent>
        </SnapPanel>
      ))}
    </>
  );
}
