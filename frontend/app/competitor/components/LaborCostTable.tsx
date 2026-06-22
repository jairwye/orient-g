"use client";

import { DataTable } from "./DataTable";
import { laborCostTableProps } from "../lib/labor_cost_table";
import type { CompetitorReportSnapshot, TableBlock } from "../lib/types";

export function LaborCostTable({
  table,
  snapshot,
  delayMs = 0,
}: {
  table: TableBlock;
  snapshot: CompetitorReportSnapshot;
  delayMs?: number;
}) {
  if (!table.rows.length) return null;
  return (
    <DataTable
      delayMs={delayMs}
      flowContent
      {...laborCostTableProps(table, snapshot)}
    />
  );
}
