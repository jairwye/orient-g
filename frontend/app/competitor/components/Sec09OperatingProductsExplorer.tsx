"use client";

import { useEffect, useMemo, useState } from "react";
import { CompanyPeekCarousel } from "./CompanyPeekCarousel";
import { DataTable } from "./DataTable";
import { colorForCompany } from "../lib/competitor_chart_colors";
import { colToLabel, companyDisplayLabel, labelToCol } from "../lib/companies";
import { CL } from "../lib/field_keys";
import { peekCarouselDwellMs } from "../lib/peek_carousel_dwell";
import { sec09FormatCell } from "../lib/sec09_table_format";
import { fillDownTableRows } from "../lib/table_fill_down";
import { useSnapFocused } from "../lib/use_snap_focused";
import { usePeekCarouselHeight } from "../lib/use_peek_carousel_height";
import type { CompetitorReportSnapshot, TableBlock } from "../lib/types";

const COMPANY_KEY_SUMMARY = "公司";
const COMPANY_KEY_DETAIL = "竞企名称";
const SNAP_ID = "sec-09-i";

function companyFromSummaryRow(row: Record<string, string | number | null>): string {
  return String(row[COMPANY_KEY_SUMMARY] ?? "").trim();
}

function detailRowsForCompany(
  detail: TableBlock,
  company: string,
): Record<string, string | number | null>[] {
  const filled = fillDownTableRows(detail.rows, detail.headers);
  return filled.filter((row) => {
    const co = String(row[COMPANY_KEY_DETAIL] ?? "").trim();
    return co === company || colToLabel(labelToCol(co) ?? co) === company;
  });
}

type Props = {
  summary: TableBlock;
  detail: TableBlock;
  snapshot: CompetitorReportSnapshot;
};

export function Sec09OperatingProductsExplorer({ summary, detail, snapshot }: Props) {
  const focused = useSnapFocused(SNAP_ID);

  const companies = useMemo(
    () => summary.rows.map((r) => companyFromSummaryRow(r)).filter(Boolean),
    [summary.rows],
  );

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

  const rowCounts = useMemo(
    () => companies.map((co) => detailRowsForCompany(detail, co).length),
    [companies, detail],
  );

  const maxRowCount = Math.max(...rowCounts, 1);

  const measurePanels = useMemo(
    () =>
      companies.map((co) => (
        <div key={co} className="w-full">
          <DataTable
            embedded
            flowContent
            headers={detail.headers}
            rows={detailRowsForCompany(detail, co)}
            compact
            wrapText
            formatCell={sec09FormatCell}
          />
        </div>
      )),
    [companies, detail],
  );

  const { heightPx: layoutLockPx, measureRef } = usePeekCarouselHeight(measurePanels, maxRowCount);

  const initialDwellMs = useMemo(
    () => peekCarouselDwellMs(rowCounts[defaultIndex] ?? 0),
    [rowCounts, defaultIndex],
  );

  const slides = useMemo(
    () =>
      companies.map((co) => ({
        id: co,
        title: `${companyDisplayLabel(co, snapshot)} · ${CL.operatingProductsDetail}`,
        content: (
          <DataTable
            embedded
            flowContent
            headers={detail.headers}
            rows={detailRowsForCompany(detail, co)}
            compact
            wrapText
            formatCell={sec09FormatCell}
          />
        ),
      })),
    [companies, detail, snapshot],
  );

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
        title={CL.operatingProducts}
        headers={summary.headers}
        rows={summary.rows}
        delayMs={40}
        compact
        wrapText
        formatCell={sec09FormatCell}
        rowAccent={(row) => colorForCompany(String(row[COMPANY_KEY_SUMMARY] ?? ""), snapshot)}
        isRowSelected={(_, i) => i === activeIndex}
        onRowClick={(_, i) => {
          setActiveIndex(i);
          setUserPaused(true);
        }}
      />
      {slides.length > 0 ? (
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
      ) : null}
    </div>
  );
}
