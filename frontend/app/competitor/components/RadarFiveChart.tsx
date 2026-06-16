"use client";

import { useMemo, useState } from "react";
import {
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import { colToLabel } from "../lib/companies";
import { colorForCompany } from "../lib/competitor_chart_colors";
import { CompetitorChartTooltip } from "./CompetitorChartTooltip";
import { FK } from "../lib/field_keys";
import { formatDecimal2, parseScore } from "../lib/format";
import {
  isAllRadarCompaniesSelected,
  toggleRadarCompanySelection,
} from "../lib/radar_company_selection";
import type { CompetitorReportSnapshot } from "../lib/types";

const RADAR_KEYS = [FK.growth, FK.profitQuality, FK.financialSafety, FK.rndInvest, FK.cashflow] as const;

type Props = {
  snapshot: CompetitorReportSnapshot;
  rows: Record<string, string | number | null>[];
};

export function RadarFiveChart({ snapshot, rows }: Props) {
  const companies = useMemo(
    () => rows.map((r) => String(r[FK.company] ?? "")).filter(Boolean),
    [rows],
  );

  const [selected, setSelected] = useState<Set<string>>(() => new Set(companies));

  const radarData = useMemo(() => {
    return RADAR_KEYS.map((dim) => {
      const point: Record<string, string | number> = { dimension: dim };
      rows.forEach((row) => {
        const name = String(row[FK.company] ?? "");
        const v = row[dim];
        if (name && typeof v === "number") point[name] = v;
        else if (name && v != null) point[name] = parseScore(v) ?? 0;
      });
      return point;
    });
  }, [rows]);

  const visible = companies.filter((c) => selected.has(c));
  const allChecked = isAllRadarCompaniesSelected(companies, selected);

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <div className="min-h-0 flex-1">
        <ResponsiveContainer width="100%" height="100%">
          <RadarChart data={radarData}>
            <PolarGrid stroke="#3f3f46" />
            <PolarAngleAxis dataKey="dimension" tick={{ fill: "#a1a1aa", fontSize: 10 }} />
            <PolarRadiusAxis angle={90} domain={[0, 100]} tick={false} />
            <Tooltip content={<CompetitorChartTooltip valueFormatter={(v) => formatDecimal2(v)} />} />
            {visible.map((name) => (
              <Radar
                key={name}
                name={name}
                dataKey={name}
                stroke={colorForCompany(name, snapshot)}
                fill={colorForCompany(name, snapshot)}
                fillOpacity={allChecked ? 0.28 : 0.42}
                strokeWidth={allChecked ? 1.5 : 2}
              />
            ))}
          </RadarChart>
        </ResponsiveContainer>
      </div>
      <ul className="flex shrink-0 flex-wrap gap-1.5 sm:gap-2" role="list">
        {companies.map((name) => {
          const checked = selected.has(name);
          const accent = colorForCompany(name, snapshot);
          const label = colToLabel(name);
          return (
            <li key={name}>
              <button
                type="button"
                role="checkbox"
                aria-checked={checked}
                onClick={() =>
                  setSelected((prev) => toggleRadarCompanySelection(companies, prev, name))
                }
                className={
                  "flex items-center gap-2 rounded-lg border px-2.5 py-1.5 text-left text-xs transition-colors " +
                  (checked
                    ? "border-zinc-600 bg-zinc-800/80 text-zinc-100"
                    : "border-zinc-800 bg-zinc-950/40 text-zinc-500 hover:border-zinc-700 hover:bg-zinc-800/40")
                }
              >
                <span
                  className={
                    "flex h-4 w-4 shrink-0 items-center justify-center rounded-[4px] border transition-colors " +
                    (checked ? "border-transparent" : "border-zinc-600 bg-zinc-900")
                  }
                  style={checked ? { backgroundColor: accent, boxShadow: `0 0 0 1px ${accent}` } : undefined}
                  aria-hidden
                >
                  {checked ? (
                    <svg viewBox="0 0 12 12" className="h-2.5 w-2.5 text-white" fill="none">
                      <path
                        d="M2.5 6.2 4.8 8.5 9.5 3.5"
                        stroke="currentColor"
                        strokeWidth="1.6"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                  ) : null}
                </span>
                <span className="truncate font-medium" style={checked ? { color: accent } : undefined}>
                  {label}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
