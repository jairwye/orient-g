import type { CompetitorReportSnapshot } from "../types";
import { colToLabel, companyDisplayLabel, labelToCol, normalizeTableCompanyKeys, SUBJECT_COL } from "../companies";

const snapSubjectLabel = {
  companies: [{ id: "yycq", label: "本公司", short: "YYCQ" }],
} as CompetitorReportSnapshot;

const snapYycqShort = {
  companies: [{ id: "yycq", label: "YYCQ", short: "YYCQ" }],
} as CompetitorReportSnapshot;

describe("companyDisplayLabel", () => {
  it("snapshot 为本公司时展示本公司", () => {
    expect(companyDisplayLabel("YYCQ", snapSubjectLabel)).toBe("本公司");
    expect(colToLabel("YYCQ", snapSubjectLabel)).toBe("本公司");
  });

  it("snapshot 为 YYCQ 时展示 YYCQ", () => {
    expect(companyDisplayLabel("YYCQ", snapYycqShort)).toBe("YYCQ");
    expect(companyDisplayLabel("本公司", snapYycqShort)).toBe("YYCQ");
  });

  it("无 snapshot 时保留入参别名", () => {
    expect(companyDisplayLabel("本公司")).toBe("本公司");
    expect(companyDisplayLabel("YYCQ")).toBe("本公司");
  });
});

describe("normalizeTableCompanyKeys", () => {
  it("保留蓝本表头原文", () => {
    const table = {
      kind: "table" as const,
      anchor: "sec-04-1",
      headers: ["指标", "本公司", "可比公司A"],
      rows: [{ 指标: "人数", 本公司: 100, 可比公司A: 200 }],
    };
    const out = normalizeTableCompanyKeys(table);
    expect(out.headers).toEqual(["指标", "本公司", "可比公司A"]);
    expect(out.rows[0]?.["本公司"]).toBe(100);
    expect(labelToCol(out.headers[1]!)).toBe(SUBJECT_COL);
  });
});
