import { buildSec09SubjectGroups } from "../sec09_subject_analysis";
import type { CompetitorReportSnapshot } from "../types";

function roiSnapshot(): CompetitorReportSnapshot {
  const headers = ["指标", "本公司", "可比公司A", "可比公司B", "可比公司C"];
  return {
    version: 1,
    meta: {},
    companies: [
      { id: "yycq", label: "本公司" },
      { id: "37", label: "可比公司A" },
      { id: "wm", label: "可比公司B" },
      { id: "zq", label: "可比公司C" },
    ],
    sections: [
      {
        id: "sec-09",
        blocks: [{ kind: "table", anchor: "sec-09-2", headers, rows: [] }],
      },
    ],
  } as CompetitorReportSnapshot;
}

describe("buildSec09SubjectGroups gov subsidy", () => {
  it("不把补助明细表标题挂到上一主体卡片", () => {
    const snap = {
      version: 1,
      meta: {},
      companies: [
        { id: "yycq", label: "本公司" },
        { id: "37", label: "可比公司A" },
        { id: "wm", label: "可比公司B" },
        { id: "zq", label: "可比公司C" },
        { id: "hq", label: "可比公司E" },
      ],
      sections: [{ id: "sec-09", blocks: [] }],
    } as CompetitorReportSnapshot;

    const md = [
      "**分析——政府补助反映政策获取能力。**",
      "",
      "可比公司E仅17.5万（残疾人就业补贴+党员活动费等），持续亏损下几乎无政府补贴。",
      "",
      "**补助明细项目（2025年）：**",
    ].join("\n");

    const groups = buildSec09SubjectGroups(md, snap);
    const hq = groups.find((g) => g.company === "可比公司E");
    expect(hq).toBeDefined();
    expect(hq!.bullets.some((b) => /补助明细项目/.test(b.text))).toBe(false);
    expect(hq!.bullets.some((b) => b.text.includes("17.5万"))).toBe(true);
  });
});

describe("buildSec09SubjectGroups ROI narrative", () => {
  it("主体卡片保留句末对比提及的其他公司名", () => {
    const md = [
      "**分析——广告费与ROI揭示获客模式。**",
      "",
      "可比公司B广告3.78亿占销售费56.8%，综合ROI 17.6x，品牌+渠道为主的发行模式，对纯买量依赖远低于可比公司A。",
    ].join("\n");

    const groups = buildSec09SubjectGroups(md, roiSnapshot());
    const wm = groups.find((g) => g.company === "可比公司B");
    expect(wm).toBeDefined();
    expect(wm!.bullets.some((b) => b.text.includes("远低于可比公司A"))).toBe(true);
    expect(groups.find((g) => g.company === "可比公司A")?.bullets ?? []).not.toEqual(
      expect.arrayContaining([expect.stringMatching(/^[。；\s]*$/)]),
    );
  });
});
