import { formatSolvencyMetricValue } from "../format";

describe("formatSolvencyMetricValue", () => {
  it("formats fraction ratios as percent per blueprint", () => {
    expect(formatSolvencyMetricValue("资产负债率", 0.388)).toBe("38.8%");
    expect(formatSolvencyMetricValue("货币资金/总资产", 0.185)).toBe("18.5%");
    expect(formatSolvencyMetricValue("有息负债率", 0.178)).toBe("17.8%");
  });

  it("keeps liquidity ratios as decimals", () => {
    expect(formatSolvencyMetricValue("流动比率", 1.16)).toBe("1.16");
    expect(formatSolvencyMetricValue("速动比率", 1.11)).toBe("1.11");
  });

  it("formats turnover and leverage with x suffix", () => {
    expect(formatSolvencyMetricValue("总资产周转率", 0.72)).toBe("0.72x");
    expect(formatSolvencyMetricValue("权益乘数", 1.65)).toBe("1.65x");
  });
});
