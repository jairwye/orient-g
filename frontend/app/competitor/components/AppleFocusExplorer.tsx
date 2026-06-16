"use client";

import { useState, type ReactNode } from "react";

export type FocusTopic = {
  id: string;
  title: string;
  content: ReactNode;
};

type Props = {
  topics: FocusTopic[];
  defaultActiveId?: string;
};

/** 左侧竖排四字选题，右侧切换内容；无内部滚动 */
export function AppleFocusExplorer({ topics, defaultActiveId }: Props) {
  const initialId = defaultActiveId ?? topics[0]?.id ?? "";
  const [activeId, setActiveId] = useState(initialId);
  const active = topics.find((t) => t.id === activeId) ?? topics[0];

  if (!topics.length) return null;

  return (
    <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:gap-5">
      <ul
        className="flex shrink-0 flex-row flex-wrap gap-1.5 lg:w-[6.5rem] lg:flex-col lg:gap-2"
        role="tablist"
        aria-label="章节选题"
      >
        {topics.map((topic) => {
          const selected = topic.id === activeId;
          return (
            <li key={topic.id} className="lg:w-full">
              <button
                type="button"
                role="tab"
                aria-selected={selected}
                onClick={() => setActiveId(topic.id)}
                className={
                  "flex w-full items-center justify-center whitespace-nowrap rounded-lg border px-2.5 py-2.5 text-center text-sm leading-none transition-colors duration-200 " +
                  (selected
                    ? "border-zinc-600/80 bg-zinc-900/55 font-medium text-zinc-100 shadow-[inset_2px_0_0_#2563eb]"
                    : "border-zinc-800/70 text-zinc-500 hover:border-zinc-700 hover:bg-zinc-900/30 hover:text-zinc-300")
                }
              >
                {topic.title}
              </button>
            </li>
          );
        })}
      </ul>

      <div className="min-w-0 flex-1" role="tabpanel">
        {active?.content}
      </div>
    </div>
  );
}
