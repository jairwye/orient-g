import type { VerticalReportSnapshot } from "../vertical_types";
import { COMPETITOR_LAST_SNAP_ID, competitorReportHref } from "../navigation";
import {
  allVerticalSnapIds,
  buildVerticalScaleEntries,
  verticalCompaniesForDisplay,
  verticalCompaniesFromReport,
  verticalReportHref,
} from "../vertical_navigation";

const sampleReport: VerticalReportSnapshot = {
  version: 1,
  meta: { title: "t", parser_version: "1", company_count: 2 },
  intro: [],
  companies: [
    { id: "37", snap_id: "v-37", name: "可比公司A", sections: [], blocks: [] },
    { id: "wm", snap_id: "v-wm", name: "可比公司B", sections: [], blocks: [] },
  ],
  warnings: [],
};

describe("vertical_navigation", () => {
  it("从 snapshot 生成导航", () => {
    expect(verticalCompaniesFromReport(sampleReport)).toHaveLength(2);
    expect(allVerticalSnapIds(sampleReport)).toContain("v-wm");
    expect(buildVerticalScaleEntries(sampleReport)[0]?.fullLabel).toBe("可比公司A");
  });

  it("详情链接 href", () => {
    expect(verticalReportHref("v-37")).toBe("/competitor/vertical#v-37");
  });

  it("返回竞品财报最后一节", () => {
    expect(COMPETITOR_LAST_SNAP_ID).toBe("sec-10-a");
    expect(competitorReportHref()).toBe("/competitor#sec-10-a");
  });

  it("详情链接展示名优先竞品 snapshot 蓝本", () => {
    const competitorSnap = {
      companies: [
        { id: "37", label: "可比公司A" },
        { id: "wm", label: "可比公司B" },
      ],
    } as import("../types").CompetitorReportSnapshot;
    const displayed = verticalCompaniesForDisplay(sampleReport, competitorSnap);
    expect(displayed[0]!.name).toBe("可比公司A");
    expect(displayed[1]!.name).toBe("可比公司B");
  });
});