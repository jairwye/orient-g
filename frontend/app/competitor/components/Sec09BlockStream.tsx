"use client";

import type { ReactNode } from "react";
import { DataTable } from "./DataTable";
import type { AnchorBlock } from "../lib/selectors";
import { sec09FormatCell, stripLicenseColumn } from "../lib/sec09_table_format";
import { fillDownTableRows } from "../lib/table_fill_down";

type FormatCellFn = (
  header: string,
  value: string | number | null,
  row?: Record<string, string | number | null>,
) => ReactNode;

function narrativePieces(markdown: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const text = markdown.trim();
  if (!text) return nodes;

  const italic = text.match(/^\*([^*]+)\*$/);
  if (italic) {
    nodes.push(
      <p key="note" className="text-xs leading-relaxed text-zinc-500">
        {italic[1]}
      </p>,
    );
    return nodes;
  }

  const heading = text.match(/^###\s+(.+)$/m);
  if (heading && !heading[1]!.startsWith("sec-")) {
    nodes.push(
      <p key="h" className="text-sm font-medium text-zinc-300">
        {heading[1]}
      </p>,
    );
  }

  const note = text.match(/^\*([^*]+)\*/m);
  if (note && !italic) {
    nodes.push(
      <p key="note" className="text-xs leading-relaxed text-zinc-500">
        {note[1]}
      </p>,
    );
  }

  return nodes;
}

function tableTitleFromContext(contextMd: string | undefined, index: number, fallback: string): string {
  if (!contextMd) return index === 0 ? fallback : `${fallback}（${index + 1}）`;
  const h = contextMd.match(/###\s+(.+)$/m)?.[1]?.trim();
  if (h && !h.startsWith("sec-")) return h;
  return index === 0 ? fallback : `${fallback}（${index + 1}）`;
}

export function Sec09BlockStream({
  blocks,
  defaultTableTitle,
  tableTitle,
  delayMs = 40,
  wrapText = false,
  hideLicenseColumn = false,
  formatCell,
  endDivider = false,
}: {
  blocks: AnchorBlock[];
  defaultTableTitle: string;
  /** 按表格序号覆盖标题 */
  tableTitle?: (index: number, prevMarkdown?: string) => string | undefined;
  delayMs?: number;
  wrapText?: boolean;
  /** 主要游戏：隐藏版号列 */
  hideLicenseColumn?: boolean;
  formatCell?: FormatCellFn;
  /** 屏末分隔线（不追加蓝本脚注） */
  endDivider?: boolean;
}) {
  if (!blocks.length) return null;

  let tableIndex = 0;
  let lastNarrative = "";
  const cellFormat = formatCell ?? sec09FormatCell;

  return (
    <div className="space-y-4 sm:space-y-5">
      {blocks.map((block, i) => {
        if (block.kind === "narrative") {
          lastNarrative = block.markdown ?? "";
          const pieces = narrativePieces(lastNarrative);
          if (!pieces.length) return null;
          return (
            <div key={`n-${i}`} className="space-y-2">
              {pieces}
            </div>
          );
        }

        const idx = tableIndex;
        tableIndex += 1;
        const title =
          tableTitle?.(idx, lastNarrative) ??
          tableTitleFromContext(lastNarrative, idx, defaultTableTitle);
        lastNarrative = "";

        let headers = block.headers;
        let rows = fillDownTableRows(block.rows, block.headers);
        if (hideLicenseColumn) {
          ({ headers, rows } = stripLicenseColumn(headers, rows));
        }

        return (
          <DataTable
            key={`t-${i}`}
            title={title}
            headers={headers}
            rows={rows}
            delayMs={delayMs + idx * 20}
            compact
            wrapText={wrapText}
            formatCell={cellFormat}
          />
        );
      })}
      {endDivider ? <div className="border-t border-zinc-800/80" aria-hidden /> : null}
    </div>
  );
}
