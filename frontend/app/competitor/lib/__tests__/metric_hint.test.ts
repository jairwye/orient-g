import { describe, expect, it } from "@jest/globals";
import { extractCompaniesHint } from "../metric_hint";

describe("extractCompaniesHint", () => {
  it("单家公司", () => {
    expect(extractCompaniesHint("1家（可比公司B）")).toBe("可比公司B");
  });

  it("多家公司", () => {
    expect(extractCompaniesHint("3家（可比公司B/可比公司A/可比公司D/本公司）")).toBe(
      "可比公司B · 可比公司A · 可比公司D · 本公司",
    );
  });
});
