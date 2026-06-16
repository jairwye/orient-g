import { extractCompaniesHint, isGrowthCompanyMetric } from "../metric_hint";

describe("extractCompaniesHint", () => {
  it("解析单家公司", () => {
    expect(extractCompaniesHint("1家（完美世界）")).toBe("完美世界");
  });

  it("解析多家公司", () => {
    expect(extractCompaniesHint("3家（完美世界/三七互娱/塔人网络/游艺春秋）")).toBe(
      "完美世界 · 三七互娱 · 塔人网络 · 游艺春秋",
    );
  });

  it("无括号返回 undefined", () => {
    expect(extractCompaniesHint("约 243.62亿")).toBeUndefined();
  });
});

describe("isGrowthCompanyMetric", () => {
  it("识别正增长公司指标", () => {
    expect(isGrowthCompanyMetric("营收正增长公司")).toBe(true);
    expect(isGrowthCompanyMetric("净利润正增长公司")).toBe(true);
    expect(isGrowthCompanyMetric("板块总盘变动")).toBe(false);
  });
});
