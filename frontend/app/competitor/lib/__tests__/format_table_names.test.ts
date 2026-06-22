import { formatTableCell, parseNum } from "../format";

describe("parseNum mixed labels", () => {
  it("does not parse game codenames", () => {
    expect(parseNum("代号MT1")).toBeNull();
    expect(parseNum("诛仙2")).toBeNull();
    expect(parseNum("DOTA2（刀塔）")).toBeNull();
  });

  it("still parses plain numbers", () => {
    expect(parseNum("1234.5")).toBe(1234.5);
    expect(parseNum("49.4%")).toBe(49.4);
    expect(parseNum("-214.6%")).toBe(-214.6);
  });
});

describe("formatTableCell name columns", () => {
  it("preserves product names with trailing digits", () => {
    expect(formatTableCell("项目名称", "代号MT1")).toBe("代号MT1");
    expect(formatTableCell("游戏名称", "诛仙2")).toBe("诛仙2");
    expect(formatTableCell("游戏名称", "DOTA2（刀塔）")).toBe("DOTA2（刀塔）");
  });

  it("formats fee ratio as percent (blueprint stores percent points)", () => {
    expect(formatTableCell("费比", 49.4)).toMatch(/49\.4/);
    expect(formatTableCell("持股比例", 15)).toMatch(/15/);
  });

  it("normalizes numeric literals to thousand separators", () => {
    expect(formatTableCell("可比公司A", "1787")).toBe("1,787");
    expect(formatTableCell("可比公司A", "1,677,793")).toBe("1,677,793");
    expect(formatTableCell("可比公司A", "-8861")).toBe("-8,861");
    expect(formatTableCell("可比公司A", "-688")).toBe("-688");
    expect(formatTableCell("可比公司A", 353833)).toBe("353,833");
  });
});
