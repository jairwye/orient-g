import { buildTopicAnalysisGroups } from "../topic_analysis";
import type { CompetitorReportSnapshot } from "../types";

function dupontSnapshot(): CompetitorReportSnapshot {
  return {
    version: 1,
    meta: {},
    companies: [
      { id: "yycq", label: "YYCQ", short: "YYCQ" },
      { id: "37", label: "可比公司A" },
    ],
    sections: [],
  } as CompetitorReportSnapshot;
}

describe("buildTopicAnalysisGroups 杜邦分主题", () => {
  it("章节分隔线 --- 不挂到上一家公司", () => {
    const md = [
      "**分析——ROE与财务安全的双重画像。**",
      "可比公司A12.6%掺了投资收益。",
      "YYCQ净现金0.78亿，是唯一以短借支撑现金的。",
      "",
      "---",
    ].join("\n");

    const groups = buildTopicAnalysisGroups(md, [], dupontSnapshot());
    const bullets = groups.flatMap((g) => g.bullets.map((b) => b.text));

    expect(bullets.some((t) => t.includes("YYCQ") && t.includes("净现金"))).toBe(true);
    expect(bullets.some((t) => t.includes("可比公司A"))).toBe(true);
    expect(bullets.some((t) => /YYCQ[：:]\s*-{2,}/.test(t) || t.trim() === "---")).toBe(false);
  });
});
