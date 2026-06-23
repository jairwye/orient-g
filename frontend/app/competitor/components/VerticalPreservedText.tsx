"use client";

import { renderBoldMarkdown } from "../lib/markdown_bold";
import { splitVerticalParagraphs } from "../lib/vertical_preserved_text";

export function VerticalPreservedText({
  markdown,
  className = "",
}: {
  markdown: string;
  className?: string;
}) {
  const blocks = splitVerticalParagraphs(markdown);

  if (!blocks.length) return null;

  return (
    <div className={`w-full max-w-none space-y-3 text-sm leading-relaxed text-zinc-400 ${className}`}>
      {blocks.map((block, i) => {
        if (block.startsWith("__subhead__:")) {
          return (
            <h4 key={i} className="pt-1 text-sm font-medium text-zinc-200">
              {block.slice("__subhead__:".length)}
            </h4>
          );
        }
        if (block.startsWith("|")) {
          return (
            <pre
              key={i}
              className="overflow-x-auto whitespace-pre-wrap break-words font-mono text-xs text-zinc-500"
            >
              {block}
            </pre>
          );
        }
        return (
          <p key={i} className="break-words">
            {renderBoldMarkdown(block)}
          </p>
        );
      })}
    </div>
  );
}
