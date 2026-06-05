"use client";

import type { ReactNode } from "react";

/** 助手消息：轻量 Markdown（表格、标题、加粗），避免管道符表格挤成一行。 */

function convertTsvTables(text: string): string {
  const lines = text.split("\n");
  const out: string[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (line.includes("\t") && line.split("\t").length - 1 >= 2) {
      const block: string[][] = [];
      while (i < lines.length) {
        const ln = lines[i];
        if (!ln.includes("\t") || ln.split("\t").length - 1 < 2) break;
        block.push(ln.split("\t").map((c) => c.trim()));
        i += 1;
      }
      if (block.length >= 2) {
        const head = block[0];
        out.push(`| ${head.join(" | ")} |`);
        out.push(`| ${head.map(() => "---").join(" | ")} |`);
        for (const row of block.slice(1)) {
          const cells = [...row, ...Array(Math.max(0, head.length - row.length)).fill("")];
          out.push(`| ${cells.slice(0, head.length).join(" | ")} |`);
        }
        continue;
      }
    }
    if (line.includes("\t")) {
      const cells = line.split("\t").map((c) => c.trim());
      if (cells.length >= 3 && cells[0] && !cells[0].startsWith("|")) {
        out.push(cells[0]);
        const rest = cells.slice(1).join("\t");
        if (rest.split("\t").length >= 2) {
          lines.splice(i + 1, 0, rest);
        }
        i += 1;
        continue;
      }
    }
    out.push(line);
    i += 1;
  }
  return out.join("\n");
}

export function normalizeAssistantMarkdown(text: string): string {
  let t = (text || "").trim();
  if (!t) return "";
  t = t.replace(/^(根据检索到的[^\n]+。\n?)/, "");
  t = convertTsvTables(t);
  t = t.replace(
    /^(华清\s*\d{4}[-、]\d{4}年销售费用[^\n]+报告)\s*$/gm,
    "## $1",
  );
  t = t.replace(/([\u4e00-\u9fff\d\-%]+报告)\s*(\d+\.)/g, "$1\n\n#### $2");
  t = t.replace(/(\|\s*—\s*\|)\s*(#{2,4})/g, "$1\n\n$2");
  t = t.replace(/(\|\s*[^\n|]+\|)\s*(#{2,4}\s*\d+\.)/g, "$1\n\n$2");
  t = t.replace(/([。；;！!?])(#{2,4})(\S)/g, "$1\n\n$2 $3");
  t = t.replace(/([\u4e00-\u9fff\）\)])(\|)/g, "$1\n\n|");
  t = t.replace(/([。；;！!?])(\d+\.\s+)/g, "$1\n\n$2");
  t = t.replace(/(\|\s*—\s*\|)\s*(结论)/g, "$1\n\n\n### $2");
  t = t.replace(/([。；;！!?])(结论[：:])/g, "$1\n\n\n**$2**");
  t = t.replace(/([。；;！!?])(引用证据)/g, "$1\n\n\n**$2**");
  t = t.replace(/([。；;！!?])(说明[：:])/g, "$1\n\n\n**$2**");
  const lines = t.split("\n").map((line) => {
    if (line.includes("|") && line.includes("||")) {
      return line.replace(/\|\s*\|/g, "|\n|");
    }
    return line;
  });
  t = lines.join("\n").replace(/\n{3,}/g, "\n\n");
  return t.trim();
}

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
  | { kind: "heading"; level: number; text: string };

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
        return null;
      })}
    </div>
  );
}
