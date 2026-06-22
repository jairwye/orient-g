import { normalizeTableCompanyKeys } from "./companies";
import type { CompetitorReportSnapshot, NarrativeBlock, TableBlock } from "./types";

export function getTable(
  snapshot: CompetitorReportSnapshot,
  anchor: string,
): TableBlock | undefined {
  return getBestTable(snapshot, anchor);
}

/** 同锚点多表时取行数最多的一张（避免旧表覆盖新分组结构） */
export function getBestTable(
  snapshot: CompetitorReportSnapshot,
  anchor: string,
): TableBlock | undefined {
  const tables = getTables(snapshot, anchor);
  if (!tables.length) return undefined;
  return tables.reduce((best, cur) =>
    cur.rows.length > best.rows.length ? cur : best,
  );
}

export function getTables(snapshot: CompetitorReportSnapshot, anchor: string): TableBlock[] {
  const out: TableBlock[] = [];
  for (const sec of snapshot.sections) {
    for (const b of sec.blocks) {
      if (b.kind === "table" && b.anchor === anchor) {
        out.push(normalizeTableCompanyKeys(b));
      }
    }
  }
  return out;
}

export type AnchorBlock = NarrativeBlock | TableBlock;

export function getAnchorBlocks(snapshot: CompetitorReportSnapshot, anchor: string): AnchorBlock[] {
  const out: AnchorBlock[] = [];
  for (const sec of snapshot.sections) {
    for (const b of sec.blocks) {
      if (b.anchor === anchor && (b.kind === "table" || b.kind === "narrative")) {
        out.push(b as AnchorBlock);
      }
    }
  }
  return out;
}

export function getNarrativeMarkdown(snapshot: CompetitorReportSnapshot, anchor: string): string {
  return getAnchorBlocks(snapshot, anchor)
    .filter((b): b is NarrativeBlock => b.kind === "narrative")
    .map((b) => b.markdown?.trim() ?? "")
    .filter(Boolean)
    .join("\n\n");
}

/** sec-09-10~15：排除小节标题/脚注，只保留分析类叙事供卡片 */
export function getAnchorAnalysisMarkdown(snapshot: CompetitorReportSnapshot, anchor: string): string {
  return getAnchorBlocks(snapshot, anchor)
    .filter((b): b is NarrativeBlock => b.kind === "narrative")
    .map((b) => b.markdown?.trim() ?? "")
    .filter((md) => {
      if (!md) return false;
      if (/^\*[^*]+\*$/.test(md)) return false;
      const first = md.split("\n")[0]?.trim() ?? "";
      if (/^###\s+/.test(first) && !/\*\*(?:简要)?分析|^分析|^总结/.test(md)) return false;
      return true;
    })
    .join("\n\n");
}

/** sec-09-3 第二张表：政府补助分项明细 */
export function getGovSubsidyDetailTable(snapshot: CompetitorReportSnapshot): TableBlock | undefined {
  const tables = getTables(snapshot, "sec-09-3");
  if (tables.length >= 2) return tables[1];
  return tables.find((t) =>
    t.headers.some((h) => h.includes("补助项目") || h.includes("主要补助") || h === "性质"),
  );
}

export function getNarrative(
  snapshot: CompetitorReportSnapshot,
  anchor: string,
): NarrativeBlock | undefined {
  for (const sec of snapshot.sections) {
    for (const b of sec.blocks) {
      if (b.kind === "narrative" && b.anchor === anchor && b.markdown?.trim()) {
        return b as NarrativeBlock;
      }
    }
  }
  return undefined;
}
export function getSection(snapshot: CompetitorReportSnapshot, id: string) {
  return snapshot.sections.find((s) => s.id === id);
}
