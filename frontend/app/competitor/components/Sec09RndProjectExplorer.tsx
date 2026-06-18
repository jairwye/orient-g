"use client";

import { useMemo } from "react";
import { AppleFocusExplorer } from "./AppleFocusExplorer";
import { DataTable } from "./DataTable";
import { sec09FormatCell } from "../lib/sec09_table_format";
import { splitTableByCompanyKey } from "../lib/sec09_company_table_split";
import type { TableBlock } from "../lib/types";

const COMPANY_KEY = "竞企名称";

type Props = {
  table: TableBlock;
};

/** 在研项目：左侧选题 + 右侧明细（同关联方交易屏） */
export function Sec09RndProjectExplorer({ table }: Props) {
  const groups = useMemo(() => splitTableByCompanyKey(table, COMPANY_KEY), [table]);

  const topics = useMemo(
    () =>
      groups.map((g) => ({
        id: g.company,
        title: g.company.length > 4 ? g.company.slice(0, 4) : g.company,
        content: (
          <DataTable
            headers={table.headers}
            rows={g.rows}
            compact
            wrapText
            flowContent
            formatCell={sec09FormatCell}
          />
        ),
      })),
    [groups, table.headers],
  );

  if (!groups.length) return null;

  return <AppleFocusExplorer topics={topics} defaultActiveId={groups[0]?.company} />;
}
