import type { CompetitorReportSnapshot, NarrativeBlock, TableBlock } from "./types";

export function getTable(
  snapshot: CompetitorReportSnapshot,
  anchor: string,
): TableBlock | undefined {
  for (const sec of snapshot.sections) {
    for (const b of sec.blocks) {
      if (b.kind === "table" && b.anchor === anchor) {
        return b;
      }
    }
  }
  return undefined;
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
