import { formatIndustryMetricValue } from "../format";

const valueKey = "值";

describe("formatIndustryMetricValue", () => {
  const annualRows = [
    { 指标: "7家公司合计营收", 值: "约 243.62亿" },
    { 指标: "含本公司合计", 值: "约 246.39亿" },
    { 指标: "板块总盘变动", 值: "约 -6.5%" },
    { 指标: "经营CF为正公司", 值: 6 },
  ];

  const interimRows = [
    { 指标: "7家公司合计营收", 值: 107.33 },
    { 指标: "含本公司合计", 值: "约 108.49亿" },
    { 指标: "板块总盘变动", 值: "约 -16.9%" },
    { 指标: "经营CF为正公司", 值: "5家（示例）" },
  ];

  it("保留已带「约…亿」的单元格", () => {
    expect(formatIndustryMetricValue("7家公司合计营收", "约 243.62亿", annualRows, valueKey)).toBe(
      "约 243.62亿",
    );
    expect(formatIndustryMetricValue("含本公司合计", "约 246.39亿", annualRows, valueKey)).toBe(
      "约 246.39亿",
    );
  });

  it("同表已有「约…亿」时，裸数字合计营收补约和亿", () => {
    expect(formatIndustryMetricValue("7家公司合计营收", 107.33, interimRows, valueKey)).toBe(
      "约 107.33亿",
    );
  });

  it("同表只有「亿」、没有「约」时只补单位", () => {
    const rows = [
      { 指标: "7家公司合计营收", 值: 107.33 },
      { 指标: "含本公司合计", 值: "108.49亿" },
    ];
    expect(formatIndustryMetricValue("7家公司合计营收", 107.33, rows, valueKey)).toBe("107.33亿");
  });

  it("没有亿级参照时不补单位", () => {
    const rows = [{ 指标: "7家公司合计营收", 值: 107.33 }];
    expect(formatIndustryMetricValue("7家公司合计营收", 107.33, rows, valueKey)).toBe("107.33");
  });

  it("家数和变动率不被当成金额", () => {
    expect(formatIndustryMetricValue("经营CF为正公司", 6, annualRows, valueKey)).toBe("6");
    expect(formatIndustryMetricValue("板块总盘变动", "约 -16.9%", interimRows, valueKey)).toBe(
      "约-16.9%",
    );
  });

  it("列头带亿且无同表样本时补亿", () => {
    const rows = [{ 指标: "7家公司合计营收", 值: 12.5 }];
    expect(formatIndustryMetricValue("7家公司合计营收", 12.5, rows, "值(亿)")).toBe("12.5亿");
  });

  it("与同表亿级样本差出两个数量级时按万元换算", () => {
    const rows = [
      { 指标: "7家公司合计营收", 值: 1_073_300 },
      { 指标: "含本公司合计", 值: "约 108.49亿" },
    ];
    expect(formatIndustryMetricValue("7家公司合计营收", 1_073_300, rows, valueKey)).toBe(
      "约 107.33亿",
    );
  });
});
