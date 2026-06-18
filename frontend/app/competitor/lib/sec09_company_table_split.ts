import { fillDownTableRows } from "./table_fill_down";
import type { TableBlock } from "./types";

/** 按「竞企名称」等列拆分明细表，保留蓝本出现顺序 */
export function splitTableByCompanyKey(
  table: TableBlock,
  companyKey: string,
): Array<{ company: string; rows: TableBlock["rows"] }> {
  const filled = fillDownTableRows(table.rows, table.headers);
  const order: string[] = [];
  const map = new Map<string, TableBlock["rows"]>();

  for (const row of filled) {
    const co = String(row[companyKey] ?? "").trim();
    if (!co || co.startsWith("**")) continue;
    if (!map.has(co)) {
      map.set(co, []);
      order.push(co);
    }
    map.get(co)!.push(row);
  }

  return order.map((company) => ({ company, rows: map.get(company)! }));
}
