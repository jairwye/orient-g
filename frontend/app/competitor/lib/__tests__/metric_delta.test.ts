import { buildMetricDelta } from "../metric_delta";

describe("buildMetricDelta", () => {
  it("升降颜色由绝对变动额决定，不受变动率符号影响", () => {
    const delta = buildMetricDelta(23465, "-8.46%");
    expect(delta.tone).toBe("up");
    expect(delta.amountText).toBe("+23,465");
    expect(delta.rateText).toBe("-8.46%");
  });

  it("仅引用传入的变动率，不自行推算", () => {
    const delta = buildMetricDelta(-147525, "+8.81%");
    expect(delta.tone).toBe("down");
    expect(delta.rateText).toBe("+8.81%");
  });

  it("ROE 变动 pct 按绝对值定色", () => {
    expect(buildMetricDelta("+0.8pct", null).tone).toBe("up");
    expect(buildMetricDelta("-5.9pct", null).tone).toBe("down");
  });
});
