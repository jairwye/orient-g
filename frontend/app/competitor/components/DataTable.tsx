import type { ReactNode } from "react";
import { formatTableCell } from "../lib/format";
import { FadeInView } from "./FadeInView";
type Props = {
  title?: string;
  subtitle?: string;
  headers: string[];
  rows: Record<string, string | number | null>[];
  delayMs?: number;
  compact?: boolean;
  highlightRow?: (row: Record<string, string | number | null>) => boolean;
  /** 行左侧色条（如公司配色） */
  rowAccent?: (row: Record<string, string | number | null>) => string | undefined;
  formatCell?: (
    header: string,
    value: string | number | null,
    row?: Record<string, string | number | null>,
  ) => ReactNode;
  /** 嵌入 ChartPanel 时去掉外层卡片与入场动效 */
  embedded?: boolean;
};

export function DataTable({
  title,
  subtitle,
  headers,
  rows,
  delayMs = 0,
  compact = false,
  highlightRow,
  rowAccent,
  formatCell = formatTableCell,
  embedded = false,
}: Props) {
  if (!rows.length) return null;

  const table = (
    <div className={embedded ? "flex min-h-0 flex-1 flex-col overflow-hidden" : "overflow-hidden rounded-lg border border-zinc-800 bg-zinc-900/50"}>
      {(title || subtitle) && !embedded ? (
        <div className="border-b border-zinc-800 px-4 py-3 md:px-5">
          {title ? <h3 className="text-sm font-medium text-zinc-300">{title}</h3> : null}
          {subtitle ? <p className="mt-0.5 text-xs text-zinc-500">{subtitle}</p> : null}
        </div>
      ) : null}
      <div className={embedded ? "min-h-0 flex-1 overflow-auto" : "overflow-x-auto"}>
          <table
            className={
              "min-w-full text-left tabular-nums text-zinc-300 " +
              (compact ? "text-xs" : "text-sm")
            }
          >
            <thead className="border-b border-zinc-800 bg-zinc-950/40 text-zinc-500">
              <tr>
                {headers.map((h) => (
                  <th key={h} className="whitespace-nowrap px-4 py-2.5 font-medium md:px-5">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => {
                const dim = highlightRow?.(row) === false;
                const accent = rowAccent?.(row);
                return (
                  <tr
                    key={i}
                    className={
                      "border-b border-zinc-800/50 transition-opacity duration-300 last:border-0 " +
                      (i % 2 === 1 ? "bg-white/[0.022]" : "") +
                      (dim ? " opacity-20" : " opacity-100")
                    }
                    style={accent ? { boxShadow: `inset 3px 0 0 ${accent}` } : undefined}
                  >
                    {headers.map((h) => (
                      <td key={h} className="whitespace-nowrap px-4 py-2.5 md:px-5">
                        {formatCell(h, row[h], row)}
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
  );

  if (embedded) return table;
  return <FadeInView delayMs={delayMs}>{table}</FadeInView>;
}

export function InsightCard({
  title,
  body,
  accent,
  delayMs = 0,
}: {
  title: string;
  body: ReactNode;
  accent?: string;
  delayMs?: number;
}) {
  return (
    <FadeInView delayMs={delayMs}>
      <div
        className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 md:p-5"
        style={accent ? { borderLeftColor: accent, borderLeftWidth: 3 } : undefined}
      >
        <p className="text-xs font-medium uppercase tracking-wide text-blue-400/90">{title}</p>
        <div className="mt-2 text-sm leading-relaxed text-zinc-300">{body}</div>
      </div>
    </FadeInView>
  );
}
