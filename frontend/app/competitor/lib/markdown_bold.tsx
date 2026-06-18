import type { ReactNode } from "react";

/** 将 `**文字**` 转为粗体，去掉星号 */
export function renderBoldMarkdown(text: string): ReactNode {
  if (!text.includes("**")) return text;
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, i) => {
    const m = part.match(/^\*\*(.+)\*\*$/);
    if (m) {
      return (
        <strong key={i} className="font-semibold text-zinc-100">
          {m[1]}
        </strong>
      );
    }
    return part ? <span key={i}>{part}</span> : null;
  });
}

export function stripMarkdownBold(text: string): string {
  return text.replace(/\*\*/g, "");
}

export function hasMarkdownBold(text: string): boolean {
  return text.includes("**");
}
