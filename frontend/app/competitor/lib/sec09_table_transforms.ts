import type { TableBlock } from "./types";

const WRAP_HEADERS = /目的|备注|项目|名称|性质|方案|变动原因|公司名称|游戏名称|主要补助|拟达到/;

export function tableHeadersNeedWrap(headers: string[]): boolean {
  return headers.some((h) => WRAP_HEADERS.test(h));
}

/** 在研项目：合并「项目目的」与「拟达到目的」为最后一列 */
export function mergeRndProjectTable(table: TableBlock): TableBlock {
  const purposeKey = "项目目的";
  const targetKey = "拟达到目的";
  if (!table.headers.includes(purposeKey) || !table.headers.includes(targetKey)) {
    return table;
  }
  const headers = table.headers.filter((h) => h !== targetKey);
  const rows = table.rows.map((row) => {
    const a = String(row[purposeKey] ?? "").trim();
    const b = String(row[targetKey] ?? "").trim();
    const merged =
      a && b && a !== "—" && b !== "—" ? `${a}；${b}` : a || b || "—";
    const next: Record<string, string | number | null> = { ...row, [purposeKey]: merged === "—" ? null : merged };
    delete next[targetKey];
    return next;
  });
  return { ...table, headers, rows };
}
