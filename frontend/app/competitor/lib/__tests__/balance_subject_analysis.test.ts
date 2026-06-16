import snapshot from "../../../../../backend/tests/fixtures/competitor_report_yycq.snapshot.json";
import { buildSubjectAnalysisGroups } from "../balance_subject_analysis";
import { buildTopicAnalysisGroups } from "../topic_analysis";
import {
  deriveAssetFpaInsights,
  deriveChangeFpaInsights,
  deriveBalanceInsights,
  deriveLiquidityFpaInsights,
} from "../finance_analysis";
import type { CompetitorReportSnapshot } from "../types";

const snap = snapshot as CompetitorReportSnapshot;

function narrativeMarkdown(anchor: string): string {
  const blocks = snap.sections.find((s) => s.id === "sec-06")?.blocks ?? [];
  const hit = blocks.find((b) => b.kind === "narrative" && b.anchor === anchor);
  if (!hit || hit.kind !== "narrative") return "";
  return hit.markdown?.trim() ?? "";
}

describe("buildSubjectAnalysisGroups", () => {
  it("screen 8 only uses sec-06-2 change narrative", () => {
    const balanceMd = narrativeMarkdown("sec-06-2");
    const insights = [...deriveAssetFpaInsights(snap), ...deriveChangeFpaInsights(snap)];

    const groups = buildSubjectAnalysisGroups(balanceMd, insights);
    const companies = groups.map((g) => g.company);
    const allText = groups.flatMap((g) => g.bullets.map((b) => b.text)).join(" ");

    expect(allText).not.toMatch(/22\.55亿|流动比率1\.16|54%应收账款老化/);
    expect(companies).toContain("三七互娱");
    expect(companies).toContain("塔人网络");
  });
});

describe("buildTopicAnalysisGroups", () => {
  it("splits sec-06-4 by bold titles and assigns liquidity narrative to 流动比率", () => {
    const md = narrativeMarkdown("sec-06-4");
    const insights = [...deriveBalanceInsights(snap), ...deriveLiquidityFpaInsights(snap)];
    const groups = buildTopicAnalysisGroups(md, insights);

    const ratioTopic = groups.find((g) => /流动比率/.test(g.title));
    expect(ratioTopic?.bullets.some((b) => b.text.includes("短期借款39.64亿"))).toBe(true);
    expect(groups.some((g) => g.bullets.some((b) => b.tag === "短期偿债"))).toBe(true);

    const netCashTopic = groups.find((g) => /净现金/.test(g.title));
    expect(netCashTopic?.bullets.some((b) => b.text.includes("掌趣科技"))).toBe(true);

    const roeTopic = groups.find((g) => /ROE|驱动力/.test(g.title));
    expect(roeTopic?.bullets.some((b) => b.tag === "ROE 排名")).toBe(true);
  });
});
