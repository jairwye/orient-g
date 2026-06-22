import { buildTopicSubjectGroups } from "../sec09_topic_subject_analysis";
import type { CompetitorReportSnapshot } from "../types";

function gameDataSnapshot(): CompetitorReportSnapshot {
  return {
    version: 1,
    meta: {},
    companies: [
      { id: "zq", label: "可比公司C" },
      { id: "la", label: "可比公司G" },
    ],
    sections: [{ id: "sec-09", blocks: [] }],
  } as CompetitorReportSnapshot;
}

describe("buildTopicSubjectGroups sec-09-11", () => {
  const briefMd = [
    "**游戏名称对应：** 游戏1=全民奇迹、游戏2=一拳超人",
    "",
    "**简要分析：** 可比公司C呈现三层产品结构——(1)全民流量型(游戏1/4)累计用户千万级、ARPU中低；(2)核心IP型(游戏2/3)ARPU极高(1,125-1,675元)、靠高付费用户驱动；(3)新游戏(游戏6/7)ARPU极高(2,019-3,742元)但用户体量极小。可比公司G蜀门全年仅新增10万用户，所有指标全线下滑，进入存量衰退。境外版本ARPU普遍低于境内，以铺量获客为主。",
  ].join("\n");

  it("展示游戏名称对应与简要分析两张主题卡", () => {
    const groups = buildTopicSubjectGroups(briefMd, gameDataSnapshot());
    expect(groups.map((g) => g.topic)).toEqual(["游戏名称对应", "简要分析"]);

    const mapping = groups[0]!;
    expect(mapping.subjects).toHaveLength(1);
    expect(mapping.subjects[0]!.company).toBe("");
    expect(mapping.subjects[0]!.bullets[0]!.text).toBe("游戏1=全民奇迹、游戏2=一拳超人");
  });

  it("简要分析按 zq / la 展示名拆分，不含境外段", () => {
    const groups = buildTopicSubjectGroups(briefMd, gameDataSnapshot());
    const brief = groups.find((g) => g.topic === "简要分析")!;
    expect(brief.subjects.map((s) => s.company)).toEqual(["可比公司C", "可比公司G"]);

    const zq = brief.subjects.find((s) => s.company === "可比公司C");
    expect(zq!.bullets[0]!.text).toMatch(/^可比公司C呈现三层产品结构/);

    const la = brief.subjects.find((s) => s.company === "可比公司G");
    expect(la!.bullets[0]!.text).toMatch(/^可比公司G蜀门全年仅新增10万用户/);
    expect(la!.bullets[0]!.text).not.toContain("境外版本");
  });
});

function productSnapshot(): CompetitorReportSnapshot {
  const companies = [
    { id: "37", label: "可比公司A" },
    { id: "wm", label: "可比公司B" },
    { id: "zq", label: "可比公司C" },
    { id: "tr", label: "可比公司D" },
    { id: "xs", label: "可比公司F" },
    { id: "la", label: "可比公司G" },
  ];
  return {
    version: 1,
    meta: {},
    companies,
    sections: [{ id: "sec-09", blocks: [] }],
  } as CompetitorReportSnapshot;
}

describe("buildTopicSubjectGroups sec-09-9 运营产品", () => {
  it("发行地区：连续「和」连接的两公司合并一行", () => {
    const md = [
      "**发行地区——全球化分层。** 可比公司A和可比公司C产品标注\"全球\"发行的比例最高，可比公司D以\"国内\"为主，可比公司B以\"中国大陆\"为核心。可比公司F100%面向中国大陆(腾讯发行)。可比公司G《蜀门》无海外版本。",
    ].join("\n");

    const groups = buildTopicSubjectGroups(md, productSnapshot());
    expect(groups).toHaveLength(1);
    expect(groups[0]!.topic).toBe("发行地区");

    const subjects = groups[0]!.subjects;
    expect(subjects[0]!.company).toBe("");
    expect(subjects[0]!.bullets[0]!.text).toContain("可比公司A和可比公司C");
    expect(subjects[0]!.bullets[0]!.text).not.toContain("可比公司D");

    expect(subjects[1]!.company).toBe("可比公司D");
    expect(subjects[2]!.company).toBe("可比公司B");
    expect(subjects[3]!.company).toBe("可比公司F");
    expect(subjects[4]!.company).toBe("可比公司G");
  });

  it("产品数量卡片删去蓝本中的 > 分隔符", () => {
    const md = [
      "**产品数量与集中度。** 可比公司A37款>可比公司D17款>可比公司B15款>可比公司C12款>可比公司F10款>游艺春秋7款>华清飞扬6款>可比公司G4款。但产品数量不等于收入贡献——可比公司G4款中《蜀门》一款贡献98.2%收入。",
    ].join("\n");

    const groups = buildTopicSubjectGroups(md, productSnapshot());
    const card = groups.find((g) => g.topic.startsWith("产品数量"))!;
    const allText = card.subjects.flatMap((s) => s.bullets.map((b) => b.text)).join("");
    expect(allText).not.toContain(">");
    expect(allText).toContain("可比公司A37款");
    expect(allText).toContain("可比公司D17款");
  });
});
