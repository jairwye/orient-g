import { buildSubjectAnalysisGroups, type SubjectAnalysisGroup } from "./balance_subject_analysis";
import { colToLabel, COMPANY_COLS, labelToCol } from "./companies";
import { FK } from "./field_keys";
import type { TableBlock } from "./types";

const COMPANY_LABELS = COMPANY_COLS.map((c) => colToLabel(c));

function resolveCompanyLabel(raw: string): string {
  const t = raw.trim();
  if (!t) return t;
  if (t === "YYCQ") return colToLabel("YYCQ");
  const hit = COMPANY_LABELS.find((l) => l === t || l.startsWith(t) || t.startsWith(l));
  return hit ?? t;
}

/** sec-07-1 叙事 + sec-07-2 盈利驱动表 → 按公司分组的解读卡片 */
export function buildProfitSubjectGroups(
  sec07_1Markdown: string,
  driversTable: TableBlock | null | undefined,
): SubjectAnalysisGroup[] {
  const base = buildSubjectAnalysisGroups(sec07_1Markdown, []);
  const bucketMap = new Map<string, SubjectAnalysisGroup>(
    base.map((g) => [g.company, { ...g, bullets: [...g.bullets] }]),
  );

  const ensure = (label: string): SubjectAnalysisGroup => {
    if (!bucketMap.has(label)) {
      bucketMap.set(label, { company: label, colKey: labelToCol(label), bullets: [] });
    }
    return bucketMap.get(label)!;
  };

  for (const row of driversTable?.rows ?? []) {
    const label = resolveCompanyLabel(String(row[FK.company] ?? ""));
    if (!label) continue;
    const conclusion = String(row["\u7ed3\u8bba"] ?? "").trim();
    const driver = String(row["\u5173\u952e\u9a71\u52a8"] ?? "").trim();
    const group = ensure(label);
    if (conclusion) {
      group.bullets.push({ text: conclusion, tag: "\u7ed3\u8bba" });
    }
    if (driver) {
      group.bullets.push({ text: driver, tag: "\u5173\u952e\u9a71\u52a8" });
    }
  }

  const order = [...base.map((g) => g.company), ...COMPANY_LABELS];
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
export function buildFeeSubjectGroups(sec07_5Markdown: string): SubjectAnalysisGroup[] {
  return buildSubjectAnalysisGroups(sec07_5Markdown, []);
}

/** sec-08-2 叙事 → 按公司分组的解读卡片 */
export function buildCashSubjectGroups(sec08_2Markdown: string): SubjectAnalysisGroup[] {
  return buildSubjectAnalysisGroups(sec08_2Markdown, []);
}
