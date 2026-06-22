import type { CompetitorReportSnapshot } from "../types";
import { colToLabel, companyDisplayLabel, labelToCol, normalizeTableCompanyKeys } from "../companies";

const snapYycqLabel = {
  companies: [{ id: "yycq", label: "游艺春秋", short: "YYCQ" }],
} as CompetitorReportSnapshot;

const snapYycqShort = {
  companies: [{ id: "yycq", label: "YYCQ", short: "YYCQ" }],
} as CompetitorReportSnapshot;

describe("companyDisplayLabel", () => {
  it("snapshot 为游艺春秋时展示游艺春秋", () => {
    expect(companyDisplayLabel("YYCQ", snapYycqLabel)).toBe("游艺春秋");
    expect(colToLabel("YYCQ", snapYycqLabel)).toBe("游艺春秋");
  });

  it("snapshot 为 YYCQ 时展示 YYCQ", () => {
    expect(companyDisplayLabel("YYCQ", snapYycqShort)).toBe("YYCQ");
    expect(companyDisplayLabel("游艺春秋", snapYycqShort)).toBe("YYCQ");
  });

  it("无 snapshot 时保留入参别名", () => {
    expect(companyDisplayLabel("游艺春秋")).toBe("游艺春秋");
    expect(companyDisplayLabel("YYCQ")).toBe("YYCQ");
  });
});

describe("normalizeTableCompanyKeys", () => {
  it("保留蓝本表头原文", () => {
    const table = {
      kind: "table" as const,
      anchor: "sec-04-1",
      headers: ["指标", "游艺春秋", "三七互娱"],
      rows: [{ 指标: "人数", 游艺春秋: 100, 三七互娱: 200 }],
    };
    const out = normalizeTableCompanyKeys(table);
    expect(out.headers).toEqual(["指标", "游艺春秋", "三七互娱"]);
    expect(out.rows[0]?.["游艺春秋"]).toBe(100);
    expect(labelToCol(out.headers[1]!)).toBe("YYCQ");
  });
});
