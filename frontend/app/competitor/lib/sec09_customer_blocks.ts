import type { AnchorBlock } from "./selectors";
import type { TableBlock } from "./types";

export type CustomerCompanyTable = {
  company: string;
  table: Pick<TableBlock, "headers" | "rows">;
};

/** sec-09-13：### 公司名 后的表格 → 分主体列表 */
export function parseCustomerCompanyTables(blocks: AnchorBlock[]): CustomerCompanyTable[] {
  const out: CustomerCompanyTable[] = [];
  let pendingCompany = "";

  for (const block of blocks) {
    if (block.kind === "narrative") {
      const md = block.markdown?.trim() ?? "";
      const h = md.match(/^###\s+(.+)$/m)?.[1]?.trim();
      if (h && !h.startsWith("sec-")) pendingCompany = h;
    } else if (block.kind === "table" && pendingCompany) {
      out.push({
        company: pendingCompany,
        table: { headers: block.headers, rows: block.rows },
      });
      pendingCompany = "";
    }
  }
  return out;
}
