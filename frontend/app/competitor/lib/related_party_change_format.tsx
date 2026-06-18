import type { ReactNode } from "react";
import { formatDecimal2, formatTableCell, parseNum } from "./format";
import { sec09FormatCell } from "./sec09_table_format";

function boldSpan(key: number, text: string) {
  return (
    <strong key={key} className="font-semibold text-zinc-100">
      {text}
    </strong>
  );
}

/** 蓝本 `**…**` → 粗体展示（数值仍走千分位/百分数格式化） */
export function renderBoldMarkdown(val: string | number | null | undefined): ReactNode {
  const raw = val == null || val === "" ? "—" : String(val).trim();
  if (!raw || raw === "—") return "—";
  if (!/\*\*/.test(raw)) return raw;

  const parts = raw.split(/(\*\*[^*]+\*\*)/g).filter(Boolean);
  return parts.map((part, i) => {
    const m = part.match(/^\*\*(.+)\*\*$/);
    if (!m) return <span key={i}>{part}</span>;
    const inner = m[1]!.trim();
    const num = parseNum(inner);
    if (num != null && /^[\d.,+%xX\-]+$/.test(inner.replace(/%/g, ""))) {
      const text = inner.endsWith("%") ? formatTableCell("", inner) : formatDecimal2(num);
      return boldSpan(i, text);
    }
    return boldSpan(i, inner);
  });
}

/** 关联方变更屏：小计行等 `**数字**` 粗体，不显示星号 */
export function relatedPartyChangeFormatCell(
  header: string,
  val: string | number | null | undefined,
): ReactNode {
  const s = String(val ?? "").trim();
  if (/\*\*/.test(s)) return renderBoldMarkdown(val);
  return sec09FormatCell(header, val);
}
