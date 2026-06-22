import { buildSubjectAnalysisGroups, type SubjectAnalysisGroup } from "./balance_subject_analysis";
import {
  colKeyForDisplayLabel,
  colToLabel,
  companyLabelsForSnapshot,
} from "./companies";
import { FK } from "./field_keys";
import type { CompetitorReportSnapshot, TableBlock } from "./types";

function resolveCompanyLabel(raw: string, snapshot?: CompetitorReportSnapshot): string {
  const t = raw.trim();
  if (!t) return t;
  if (t === "YYCQ") return colToLabel("YYCQ", snapshot);
  const labels = companyLabelsForSnapshot(snapshot);
  const hit = labels.find((l) => l === t || l.startsWith(t) || t.startsWith(l));
  return hit ?? t;
}

/** sec-07-1 叙事 + sec-07-2 盈利驱动表 → 按公司分组的解读卡片 */
export function buildProfitSubjectGroups(
  sec07_1Markdown: string,
  driversTable: TableBlock | null | undefined,
  snapshot?: CompetitorReportSnapshot,
): SubjectAnalysisGroup[] {
  const base = buildSubjectAnalysisGroups(sec07_1Markdown, [], snapshot);
  const bucketMap = new Map<string, SubjectAnalysisGroup>(
    base.map((g) => [g.company, { ...g, bullets: [...g.bullets] }]),
  );

  const ensure = (label: string): SubjectAnalysisGroup => {
    if (!bucketMap.has(label)) {
      bucketMap.set(label, {
        company: label,
        colKey: colKeyForDisplayLabel(label, snapshot),
        bullets: [],
      });
    }
    return bucketMap.get(label)!;
  };

  for (const row of driversTable?.rows ?? []) {
    const label = resolveCompanyLabel(String(row[FK.company] ?? ""), snapshot);
    if (!label) continue;
    const conclusion = String(row["结论"] ?? "").trim();
    const driver = String(row["关键驱动"] ?? "").trim();
    const group = ensure(label);
    if (conclusion) {
      group.bullets.push({ text: conclusion, tag: "结论" });
    }
    if (driver) {
      group.bullets.push({ text: driver, tag: "关键驱动" });
    }
  }

  const order = [...base.map((g) => g.company), ...companyLabelsForSnapshot(snapshot)];
  const seen = new Set<string>();
  return order
    .filter((co) => {
      if (seen.has(co)) return false;
      seen.add(co);
      return (bucketMap.get(co)?.bullets.length ?? 0) > 0;
    })
    .map((co) => bucketMap.get(co)!);
}

/** sec-07-5 叙事 → 按公司分组的解读卡片（仅蓝本文字） */
export function buildFeeSubjectGroups(
  sec07_5Markdown: string,
  snapshot?: CompetitorReportSnapshot,
): SubjectAnalysisGroup[] {
  return buildSubjectAnalysisGroups(sec07_5Markdown, [], snapshot);
}

/** sec-08-2 叙事 → 按公司分组的解读卡片 */
export function buildCashSubjectGroups(
  sec08_2Markdown: string,
  snapshot?: CompetitorReportSnapshot,
): SubjectAnalysisGroup[] {
  return buildSubjectAnalysisGroups(sec08_2Markdown, [], snapshot);
}
