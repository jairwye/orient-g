"use client";

import { useEffect, useMemo, useState } from "react";
import { CompanyPeekCarousel } from "./CompanyPeekCarousel";
import { DataTable } from "./DataTable";
import { colorForCompany } from "../lib/competitor_chart_colors";
import { CL } from "../lib/field_keys";
import { peekCarouselDwellMs } from "../lib/peek_carousel_dwell";
import { sec09FormatCell } from "../lib/sec09_table_format";
import { useSnapFocused } from "../lib/use_snap_focused";
import { usePeekCarouselHeight } from "../lib/use_peek_carousel_height";
import type { AnchorBlock } from "../lib/selectors";
import type { CompetitorReportSnapshot, TableBlock } from "../lib/types";

import { parseCustomerCompanyTables } from "../lib/sec09_customer_blocks";

const SNAP_ID = "sec-09-m";

type CompanyTable = { company: string; table: Pick<TableBlock, "headers" | "rows"> };

function parseCustomerBlocks(blocks: AnchorBlock[]): CompanyTable[] {
  return parseCustomerCompanyTables(blocks);
}

type Props = {
  blocks: AnchorBlock[];
  snapshot: CompetitorReportSnapshot;
};

export function Sec09CustomerExplorer({ blocks, snapshot }: Props) {
  const focused = useSnapFocused(SNAP_ID);
  const companyTables = useMemo(() => parseCustomerBlocks(blocks), [blocks]);

  const summaryRows = useMemo(
    () =>
      companyTables.map((c) => ({
        公司: c.company,
        明细条数: c.table.rows.length,
      })),
    [companyTables],
  );

  const companies = useMemo(() => companyTables.map((c) => c.company), [companyTables]);

  const defaultIndex = useMemo(() => {
    const preferred = snapshot.companies
      .filter((c) => c.id !== "yycq")
      .map((c) => c.label)
      .find((label) => companies.includes(label));
    const i = preferred ? companies.indexOf(preferred) : 0;
    return i >= 0 ? i : 0;
  }, [companies, snapshot]);

  const [activeIndex, setActiveIndex] = useState(defaultIndex);
  const [userPaused, setUserPaused] = useState(false);
  const [activationKey, setActivationKey] = useState(0);

  useEffect(() => {
    if (focused) {
      setActiveIndex(defaultIndex);
      setUserPaused(false);
      setActivationKey((k) => k + 1);
    }
  }, [focused, defaultIndex]);

  const rowCounts = useMemo(() => companyTables.map((c) => c.table.rows.length), [companyTables]);
  const maxRowCount = Math.max(...rowCounts, 1);

  const measurePanels = useMemo(
    () =>
      companyTables.map((c) => (
        <div key={c.company} className="w-full">
          <DataTable
            embedded
            flowContent
            headers={c.table.headers}
            rows={c.table.rows}
            compact
            wrapText
            formatCell={sec09FormatCell}
          />
        </div>
      )),
    [companyTables],
  );

  const { heightPx: layoutLockPx, measureRef } = usePeekCarouselHeight(measurePanels, maxRowCount);

  const initialDwellMs = useMemo(
    () => peekCarouselDwellMs(rowCounts[defaultIndex] ?? 0),
    [rowCounts, defaultIndex],
  );

  const slides = useMemo(
    () =>
      companyTables.map((c) => ({
        id: c.company,
        title: `${c.company} · 重要客商明细`,
        content: (
          <DataTable
            embedded
            flowContent
            headers={c.table.headers}
            rows={c.table.rows}
            compact
            wrapText
            formatCell={sec09FormatCell}
          />
        ),
      })),
    [companyTables],
  );

  if (!companyTables.length) return null;

  return (
    <div className="relative space-y-5 sm:space-y-6">
      <div
        ref={measureRef}
        className="pointer-events-none absolute left-[8%] top-0 -z-10 w-[84%] opacity-0"
        aria-hidden
      >
        {measurePanels}
      </div>
      <DataTable
        title={CL.majorCustomers}
        headers={["公司", "明细条数"]}
        rows={summaryRows}
        compact
        rowAccent={(row) => colorForCompany(String(row["公司"] ?? ""), snapshot)}
        isRowSelected={(_, i) => i === activeIndex}
        onRowClick={(_, i) => {
          setActiveIndex(i);
          setUserPaused(true);
        }}
      />
      <div style={!focused ? { minHeight: layoutLockPx } : undefined}>
        <CompanyPeekCarousel
          slides={slides}
          activeIndex={activeIndex}
          onActiveIndexChange={setActiveIndex}
          onUserNavigate={() => setUserPaused(true)}
          onResume={() => setUserPaused(false)}
          userPaused={userPaused}
          paused={userPaused || !focused}
          activated={focused}
          activationKey={activationKey}
          initialDwellMs={initialDwellMs}
        />
      </div>
    </div>
  );
}
