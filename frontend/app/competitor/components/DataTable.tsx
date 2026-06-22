import type { ReactNode } from "react";
import { formatTableCell, formatTableCellForRow } from "../lib/format";
import { resolveTableHeaderKeys } from "../lib/table_header_keys";
import { FadeInView } from "./FadeInView";
type Props = {
  title?: string;
  subtitle?: string;
  headers: string[];
  /** 与 headers 等长；重复表头列的唯一 row 键 */
  headerKeys?: string[];
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
  /** 嵌入轮播面板时去掉外层卡片与入场动效 */
  embedded?: boolean;
  /** 表格自然撑开，不出现内滚动条 */
  flowContent?: boolean;
  /** 长文本列自动换行（目的、备注等） */
  wrapText?: boolean;
  onRowClick?: (row: Record<string, string | number | null>, index: number) => void;
  isRowSelected?: (row: Record<string, string | number | null>, index: number) => boolean;
  /** 分组标题行（如 sec-04-3 **人力成本**）：整行合并为一格 */
  isSectionHeaderRow?: (row: Record<string, string | number | null>) => boolean;
  rowLabelHeader?: string;
  /** 表头展示文案（行键仍用 headers 原值） */
  headerDisplay?: (header: string) => string;
  /** 单元格取值（默认 row[header]；宽表 本公司/YYCQ 等需别名时使用） */
  getCellValue?: (
    header: string,
    row: Record<string, string | number | null>,
  ) => string | number | null | undefined;
  sectionHeaderClassName?: string;
};

export function DataTable({
  title,
  subtitle,
  headers,
  headerKeys,
  rows,
  delayMs = 0,
  compact = false,
  highlightRow,
  rowAccent,
  formatCell,
  embedded = false,
  flowContent = false,
  wrapText = false,
  onRowClick,
  isRowSelected,
  isSectionHeaderRow,
  rowLabelHeader,
  headerDisplay,
  getCellValue,
  sectionHeaderClassName,
}: Props) {
  if (!rows.length) return null;

  const columnKeys = resolveTableHeaderKeys(headers, headerKeys);
  const labelHeader = rowLabelHeader ?? headers[0] ?? "";
  const labelKey = columnKeys[0] ?? labelHeader;
  const cellFormatter =
    formatCell ?? ((h, v, row) => formatTableCellForRow(h, v, row, labelHeader));

  const wrapCol = (h: string) => wrapText || /目的|备注|项目|名称|性质|方案|变动|公司名称|游戏名称|主要补助|拟达到|交易类型|备注/.test(h);

  const isLabelColumn = (h: string, colIndex: number) => colIndex === 0 || wrapCol(h);

  const table = (
    <div
      className={
        embedded
          ? flowContent
            ? ""
            : "flex min-h-0 flex-1 flex-col overflow-hidden"
          : flowContent
            ? "rounded-lg border border-zinc-800 bg-zinc-900/50"
            : "overflow-hidden rounded-lg border border-zinc-800 bg-zinc-900/50"
      }
    >
      {(title || subtitle) && !embedded ? (
        <div className="border-b border-zinc-800 px-4 py-3 md:px-5">
          {title ? <h3 className="text-sm font-medium text-zinc-300">{title}</h3> : null}
          {subtitle ? <p className="mt-0.5 text-xs text-zinc-500">{subtitle}</p> : null}
        </div>
      ) : null}
      <div
        className={
          embedded
            ? flowContent
              ? "overflow-visible"
              : "min-h-0 flex-1 overflow-auto"
            : "overflow-x-auto"
        }
      >
          <table
            className={
              "min-w-full tabular-nums text-zinc-300 " +
              (compact ? "text-xs" : "text-sm")
            }
          >
            <thead className="border-b border-zinc-800 bg-zinc-950/40 text-zinc-500">
              <tr>
                {headers.map((h, colIndex) => (
                  <th
                    key={`col-${colIndex}-${columnKeys[colIndex] ?? h}`}
                    className={
                      "whitespace-nowrap px-4 py-2.5 font-medium md:px-5 " +
                      (isLabelColumn(h, colIndex) ? "text-left" : "text-right")
                    }
                  >
                    {headerDisplay ? headerDisplay(h) : h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => {
                if (isSectionHeaderRow?.(row)) {
                  return (
                    <tr
                      key={i}
                      className={
                        "border-b border-zinc-800/50 bg-zinc-950/55 " + (sectionHeaderClassName ?? "")
                      }
                    >
                      <td
                        colSpan={headers.length}
                        className="px-4 py-2.5 font-semibold text-zinc-100 md:px-5"
                      >
                        {cellFormatter(
                          labelHeader,
                          (getCellValue ? getCellValue(labelKey, row) : row[labelKey]) ?? null,
                          row,
                        )}
                      </td>
                    </tr>
                  );
                }
                const dim = highlightRow?.(row) === false;
                const accent = rowAccent?.(row);
                const selected = isRowSelected?.(row, i) ?? false;
                const clickable = Boolean(onRowClick);
                const stripe = !selected && i % 2 === 1;
                return (
                  <tr
                    key={i}
                    onClick={clickable ? () => onRowClick!(row, i) : undefined}
                    className={
                      "border-b border-zinc-800/50 transition-[opacity,background-color,font-weight,color] duration-300 last:border-0 " +
                      (stripe ? " bg-white/[0.022]" : "") +
                      (dim ? " opacity-20" : " opacity-100") +
                      (clickable ? " cursor-pointer hover:bg-zinc-800/35" : "") +
                      (selected ? " bg-blue-950/45 font-semibold text-zinc-100 hover:bg-blue-950/45" : "")
                    }
                    style={accent ? { boxShadow: `inset 3px 0 0 ${accent}` } : undefined}
                  >
                    {headers.map((h, colIndex) => {
                      const colKey = columnKeys[colIndex] ?? h;
                      const cellVal = getCellValue ? getCellValue(colKey, row) : row[colKey];
                      return (
                      <td
                        key={`col-${colIndex}-${colKey}`}
                        className={
                          "px-4 py-2.5 md:px-5 " +
                          (isLabelColumn(h, colIndex) ? "text-left " : "text-right ") +
                          (wrapCol(h) ? "max-w-[280px] whitespace-normal break-words align-top" : "whitespace-nowrap")
                        }
                      >
                        {cellFormatter(h, cellVal ?? null, row)}
                      </td>
                    );
                    })}
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
