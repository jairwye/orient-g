/** 纵向对比页：公司 snap 导航（数据来自 GET /api/competitor/vertical-report） */
import { runtimeCompanyDisplayName } from "./companies";
import type { CompetitorReportSnapshot } from "./types";
import type { VerticalReportSnapshot } from "./vertical_types";

export type VerticalCompanyNav = {
  id: string;
  snapId: string;
  name: string;
};

export type VerticalScaleEntry = {
  snapId: string;
  fullLabel: string;
  kind: "main" | "sub";
};

export function verticalCompaniesFromReport(data: VerticalReportSnapshot): VerticalCompanyNav[] {
  return (data.companies ?? []).map((c) => ({
    id: c.id,
    snapId: c.snap_id,
    name: c.name,
  }));
}

/** 纵向目录 + 竞品 snapshot：页面展示用蓝本主体名 */
export function verticalCompaniesForDisplay(
  vertical: VerticalReportSnapshot,
  competitorSnapshot?: CompetitorReportSnapshot,
): VerticalCompanyNav[] {
  return verticalCompaniesFromReport(vertical).map((c) => ({
    ...c,
    name: runtimeCompanyDisplayName(c.id, competitorSnapshot, c.name),
  }));
}

export function allVerticalSnapIds(data: VerticalReportSnapshot): string[] {
  const intro = (data.intro?.length ?? 0) > 0 ? ["v-intro"] : [];
  return [...intro, ...(data.companies ?? []).map((c) => c.snap_id)];
}

export function buildVerticalScaleEntries(
  data: VerticalReportSnapshot,
  competitorSnapshot?: CompetitorReportSnapshot,
): VerticalScaleEntry[] {
  return buildVerticalScaleEntriesFromCompanies(
    verticalCompaniesForDisplay(data, competitorSnapshot),
  );
}

export function buildVerticalScaleEntriesFromCompanies(
  companies: VerticalCompanyNav[],
): VerticalScaleEntry[] {
  return companies.map((c) => ({
    snapId: c.snapId,
    fullLabel: c.name,
    kind: "main" as const,
  }));
}

export function verticalCompanyBySnap(
  data: VerticalReportSnapshot,
  snapId: string,
): VerticalCompanyNav | undefined {
  return verticalCompaniesFromReport(data).find((c) => c.snapId === snapId);
}

/** 竞品财报「详情链接」→ 纵向对比页锚点 */
export function verticalReportHref(snapId: string): string {
  return `/competitor/vertical#${snapId}`;
}
