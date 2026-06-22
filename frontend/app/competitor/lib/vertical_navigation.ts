/** 纵向对比页：公司 snap 导航（数据来自 GET /api/competitor/vertical-report） */
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

export function allVerticalSnapIds(data: VerticalReportSnapshot): string[] {
  const intro = (data.intro?.length ?? 0) > 0 ? ["v-intro"] : [];
  return [...intro, ...(data.companies ?? []).map((c) => c.snap_id)];
}

export function buildVerticalScaleEntries(data: VerticalReportSnapshot): VerticalScaleEntry[] {
  return verticalCompaniesFromReport(data).map((c) => ({
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
