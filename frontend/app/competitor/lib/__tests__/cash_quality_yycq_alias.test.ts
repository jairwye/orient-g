import { parseCashQualityPoints } from "../finance_analysis";
import type { CompetitorReportSnapshot } from "../types";

function snapshotWithYycqLabelHeader(): CompetitorReportSnapshot {
  return {
    version: 1,
    meta: {},
    companies: [{ id: "yycq", label: "游艺春秋", short: "YYCQ" }],
    sections: [
      {
        id: "sec-08",
        title: "现金流",
        blocks: [
          {
            kind: "table",
            anchor: "sec-08-2",
            headers: ["指标", "游艺春秋", "三七互娱"],
            rows: [
              { 指标: "净利润(万)", 游艺春秋: 5698, 三七互娱: 289895 },
              { 指标: "经营CF(万)", 游艺春秋: 2864, 三七互娱: 353833 },
              { 指标: "经营CF/净利", 游艺春秋: "41.4%", 三七互娱: "122.1%" },
            ],
          },
        ],
      },
    ],
  } as CompetitorReportSnapshot;
}

describe("parseCashQualityPoints YYCQ alias", () => {
  it("表头为「游艺春秋」时仍解析出游艺春秋分级点", () => {
    const points = parseCashQualityPoints(snapshotWithYycqLabelHeader());
    const yycq = points.find((p) => p.colKey === "YYCQ");
    expect(yycq).toBeDefined();
    expect(yycq!.name).toBe("游艺春秋");
    expect(yycq!.profit).toBe(5698);
    expect(yycq!.ocf).toBe(2864);
  });
});
