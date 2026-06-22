import { buildCashSubjectGroups } from "../profit_subject_analysis";
import type { CompetitorReportSnapshot } from "../types";

const SEC08_MARKDOWN = `
本公司（56.2%）经营现金流低于净利润，负向差异2,229万。

可比公司A（122.1%）利润含金量良好，正向差异63,938万来自资产减值准备、折旧摊销等非现金项目。

可比公司B（157.9%）经营现金流远超净利润，含金量最高，"正向剪刀差"说明盈利质量高。

可比公司C（4.4%）减值损失导致净利润大幅亏损，但经营现金流仅微负。

可比公司G（-84.1%）唯一净利润为正但经营现金流为负的公司，核心原因：经营性应付项目大降。

**综合判断：** 可比公司B157.9%和可比公司A122.1%的利润是真金白银；可比公司F153.3%是会计处理虚高（研发资本化）；可比公司G-84.1%暴露了利润背后的现金流恶化；可比公司C4.4%揭示亏损主因是一次性减值而非经营恶化。

2025年游戏行业"谁在真正赚钱"的答案，现金流量表给出了比利润表更诚实的回答。
`.trim();

function cashflowSnapshot(): CompetitorReportSnapshot {
  const headers = [
    "指标",
    "本公司",
    "可比公司A",
    "可比公司B",
    "可比公司C",
    "可比公司D",
    "可比公司E",
    "可比公司F",
    "可比公司G",
  ];
  return {
    version: 1,
    meta: {},
    companies: headers.slice(1).map((label, i) => ({
      id: i === 0 ? "yycq" : ["37", "wm", "zq", "tr", "hq", "xs", "la"][i - 1] ?? `peer-${i}`,
      label,
    })),
    sections: [
      {
        id: "sec-08",
        title: "现金流",
        blocks: [{ kind: "table", anchor: "sec-08-2", headers, rows: [] }],
      },
    ],
  } as CompetitorReportSnapshot;
}

describe("buildCashSubjectGroups sec-08-2", () => {
  it("按主体拆分叙事，综合判断不残留碎片或标题行", () => {
    const groups = buildCashSubjectGroups(SEC08_MARKDOWN, cashflowSnapshot());
    const byCompany = Object.fromEntries(groups.map((g) => [g.company, g.bullets.map((b) => b.text)]));

    expect(byCompany["可比公司B"]).toEqual(
      expect.arrayContaining([
        expect.stringContaining("经营现金流远超净利润"),
        expect.stringContaining("157.9%的利润是真金白银"),
      ]),
    );
    expect(byCompany["可比公司A"]).toEqual(
      expect.arrayContaining([
        expect.stringContaining("利润含金量良好"),
        expect.stringContaining("122.1%的利润是真金白银"),
      ]),
    );
    expect(byCompany["可比公司G"]).toEqual(
      expect.arrayContaining([expect.stringContaining("唯一净利润为正但经营现金流为负")]),
    );
    expect(byCompany["可比公司F"]).toEqual(
      expect.arrayContaining([expect.stringContaining("会计处理虚高")]),
    );

    for (const bullets of Object.values(byCompany)) {
      for (const text of bullets) {
        expect(text).not.toMatch(/^157\.9%和$/);
        expect(text).not.toMatch(/^综合判断[：:]?$/);
      }
    }
  });
});
