"use client";

import type { ReactNode } from "react";
import { normalizeAssistantMarkdown } from "./markdownNormalize";

/** 助手消息：轻量 Markdown（表格、标题、加粗），避免管道符表格挤成一行。 */

function isTableSeparator(line: string): boolean {
  const t = line.trim();
  return Boolean(t) && /^[\|\s:\-]+$/.test(t) && t.includes("|");
}

function parseTableRow(line: string): string[] {
  return line
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((c) => c.trim());
}

type Block =
  | { kind: "para"; text: string }
  | { kind: "table"; rows: string[][] }
  | { kind: "heading"; level: number; text: string }
  | { kind: "list"; items: string[] };

function parseBlocks(text: string): Block[] {
  const blocks: Block[] = [];
  const lines = (text || "").split("\n");
  let i = 0;
  let paraBuf: string[] = [];

  const flushPara = () => {
    const joined = paraBuf.join("\n").trim();
    paraBuf = [];
    if (joined) blocks.push({ kind: "para", text: joined });
  };

  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();
    if (!trimmed) {
      flushPara();
      i += 1;
      continue;
    }
    const hm = trimmed.match(/^(#{1,4})\s*(.+)$/);
    if (hm) {
      flushPara();
      blocks.push({ kind: "heading", level: hm[1].length, text: hm[2].trim() });
      i += 1;
      continue;
    }
    if (/^-\s+/.test(trimmed)) {
      flushPara();
      const items: string[] = [];
      while (i < lines.length) {
        const ln = lines[i].trim();
        if (!ln) break;
        const bm = ln.match(/^-\s+(.*)$/);
        if (!bm) break;
        items.push(bm[1].trim());
        i += 1;
      }
      if (items.length) blocks.push({ kind: "list", items });
      continue;
    }
    if (
      trimmed.includes("|") &&
      i + 1 < lines.length &&
      isTableSeparator(lines[i + 1])
    ) {
      flushPara();
      const rows: string[][] = [parseTableRow(line)];
      i += 2;
      while (i < lines.length && lines[i].trim().includes("|")) {
        rows.push(parseTableRow(lines[i]));
        i += 1;
      }
      blocks.push({ kind: "table", rows });
      continue;
    }
    paraBuf.push(line);
    i += 1;
  }
  flushPara();
  return blocks;
}

function renderInline(text: string): ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((p, idx) => {
    if (p.startsWith("**") && p.endsWith("**")) {
      return (
        <strong key={idx} className="font-semibold text-zinc-100">
          {p.slice(2, -2)}
        </strong>
      );
    }
    return <span key={idx}>{p}</span>;
  });
}

export function MarkdownBubble({ text }: { text: string }) {
  const blocks = parseBlocks(normalizeAssistantMarkdown(text));
  if (!blocks.length) return null;

  return (
    <div className="space-y-3 text-sm leading-relaxed text-zinc-200">
      {blocks.map((b, idx) => {
        if (b.kind === "heading") {
          const Tag = b.level <= 2 ? "h3" : "h4";
          return (
            <Tag
              key={idx}
              className={
                b.level <= 2
                  ? "text-base font-semibold text-zinc-100"
                  : "text-sm font-medium text-zinc-100"
              }
            >
              {renderInline(b.text)}
            </Tag>
          );
        }
        if (b.kind === "table" && b.rows.length) {
          const [head, ...body] = b.rows;
          return (
            <div key={idx} className="overflow-x-auto rounded-lg border border-zinc-700/80">
              <table className="min-w-full border-collapse text-left text-xs md:text-sm">
                <thead className="bg-zinc-800/80">
                  <tr>
                    {head.map((cell, ci) => (
                      <th
                        key={ci}
                        className="whitespace-nowrap border-b border-zinc-700 px-3 py-2 font-medium text-zinc-100"
                      >
                        {renderInline(cell)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {body.map((row, ri) => (
                    <tr key={ri} className="even:bg-zinc-900/40">
                      {row.map((cell, ci) => (
                        <td
                          key={ci}
                          className="border-b border-zinc-800/80 px-3 py-2 align-top text-zinc-200"
                        >
                          {renderInline(cell)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        }
        if (b.kind === "para") {
          return (
            <p key={idx} className="whitespace-pre-wrap break-words [overflow-wrap:anywhere]">
              {renderInline(b.text)}
            </p>
          );
        }
        if (b.kind === "list") {
          return (
            <ul key={idx} className="list-disc space-y-1.5 pl-5 text-zinc-200">
              {b.items.map((item, li) => (
                <li key={li} className="leading-relaxed">
                  {renderInline(item)}
                </li>
              ))}
            </ul>
          );
        }
        return null;
      })}
    </div>
  );
}
