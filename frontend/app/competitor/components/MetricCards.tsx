import { KPICard } from "./KPICard";
import { colorForCompany } from "../lib/competitor_chart_colors";
import type { CompetitorReportSnapshot } from "../lib/types";
import { FK } from "../lib/field_keys";
import { formatTableCell } from "../lib/format";
import { extractCompaniesHint, isGrowthCompanyMetric } from "../lib/metric_hint";
import { colToLabel } from "../lib/companies";
import { FadeInView } from "./FadeInView";

type Row = Record<string, string | number | null>;

/** sec-01-1 等行业指标：键值表 → KPI 卡片网格 */
export function MetricCardGrid({
  rows,
  labelKey = FK.metric,
  valueKey = FK.value,
  prominent = false,
}: {
  rows: Row[];
  labelKey?: string;
  valueKey?: string;
  /** 首屏加大卡片与间距 */
  prominent?: boolean;
}) {
  if (!rows.length) return null;

  return (
    <div
      className={
        prominent
          ? "grid gap-4 sm:grid-cols-2 sm:gap-5 lg:grid-cols-3 lg:gap-6"
          : "grid gap-3 sm:grid-cols-2 lg:grid-cols-3"
      }
    >
      {rows.map((row, i) => {
        const label = String(row[labelKey] ?? "");
        const rawValue = row[valueKey];
        const hint =
          isGrowthCompanyMetric(label) ? extractCompaniesHint(rawValue) : undefined;

        return (
          <KPICard
            key={i}
            label={label}
            value={formatTableCell(valueKey, rawValue)}
            hint={hint}
            delayMs={i * 60}
            prominent={prominent}
          />
        );
      })}
    </div>
  );
}

/** sec-01-2 等公司 KPI 摘要：每公司一张信息卡片 */
export function CompanyKpiCards({
  rows,
  snapshot,
}: {
  rows: Row[];
  snapshot: CompetitorReportSnapshot;
}) {
  if (!rows.length) return null;

  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {rows.map((row, i) => {
        const rawName = String(row[FK.company] ?? "");
        const name = colToLabel(rawName, snapshot) || rawName;
        const accent = colorForCompany(rawName, snapshot);
        const tag = row["标签"] != null ? String(row["标签"]) : "";
        const fields = Object.entries(row).filter(([k]) => k !== FK.company && k !== "标签");

        return (
          <FadeInView key={name || i} delayMs={i * 50}>
            <div
              className="flex h-full flex-col rounded-lg border border-zinc-800 bg-zinc-900/50 p-4"
              style={{ borderTopColor: accent, borderTopWidth: 2 }}
            >
              <div className="flex items-start justify-between gap-2">
                <p className="text-sm font-medium text-zinc-100">{name}</p>
                {tag ? (
                  <span className="shrink-0 rounded border border-zinc-700/80 bg-zinc-950/80 px-1.5 py-0.5 text-[10px] text-zinc-400">
                    {tag}
                  </span>
                ) : null}
              </div>
              <dl className="mt-3 flex-1 space-y-2">
                {fields.map(([key, val]) => (
                  <div key={key} className="flex items-baseline justify-between gap-2 text-xs">
                    <dt className="shrink-0 text-zinc-500">{key}</dt>
                    <dd className="tabular-nums text-right font-medium text-zinc-200">
                      {formatTableCell(key, val)}
                    </dd>
                  </div>
                ))}
              </dl>
            </div>
          </FadeInView>
        );
      })}
    </div>
  );
}
