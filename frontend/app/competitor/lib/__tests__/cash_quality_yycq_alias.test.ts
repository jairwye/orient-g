import { parseCashQualityPoints } from "../finance_analysis";
import { SUBJECT_COL } from "../companies";
import type { CompetitorReportSnapshot } from "../types";

function snapshotWithSubjectLabelHeader(): CompetitorReportSnapshot {
  return {
    version: 1,
    meta: {},
    companies: [{ id: "yycq", label: "本公司", short: "YYCQ" }],
    sections: [
      {
        id: "sec-08",
        title: "现金流",
        blocks: [
          {
            kind: "table",
            anchor: "sec-08-2",
            headers: ["指标", "本公司", "可比公司A"],
            rows: [
              { 指标: "净利润(万)", 本公司: 5698, 可比公司A: 289895 },
              { 指标: "经营CF(万)", 本公司: 2864, 可比公司A: 353833 },
              { 指标: "经营CF/净利", 本公司: "41.4%", 可比公司A: "122.1%" },
            ],
          },
        ],
      },
    ],
  } as CompetitorReportSnapshot;
}

describe("parseCashQualityPoints subject alias", () => {
  it("表头为本公司时仍解析出主体分级点，页面展示 YYCQ", () => {
    const points = parseCashQualityPoints(snapshotWithSubjectLabelHeader());
    const subject = points.find((p) => p.colKey === SUBJECT_COL || p.colKey === "本公司");
    expect(subject).toBeDefined();
    expect(subject!.name).toBe("YYCQ");
    expect(subject!.profit).toBe(5698);
    expect(subject!.ocf).toBe(2864);
  });
});
