import {
  formatDecimal2,
  formatPct,
  formatPercentFromPoints,
  formatTableCell,
  formatTableCellForRow,
  toPercentPoints,
} from "../format";

describe("toPercentPoints", () => {
  it("小数比例（旧 snapshot / 无 % 列）", () => {
    expect(toPercentPoints(0.494)).toBe(49.4);
    expect(toPercentPoints(0.088)).toBe(8.8);
  });

  it("已是百分点（新 snapshot / 蓝本带 %）", () => {
    expect(toPercentPoints(-214.6)).toBe(-214.6);
    expect(toPercentPoints(41.4)).toBe(41.4);
    expect(toPercentPoints(122.1)).toBe(122.1);
    expect(toPercentPoints(5.1)).toBe(5.1);
    expect(toPercentPoints(5.0)).toBe(5.0);
    expect(toPercentPoints(4.9)).toBe(4.9);
  });

  it("旧 snapshot 大百分比被 /100 后", () => {
    expect(toPercentPoints(-2.146)).toBe(-214.6);
    expect(toPercentPoints(1.221)).toBe(122.1);
  });
});

describe("formatPct", () => {
  it("保留蓝本一位小数", () => {
    expect(formatPct(-214.6)).toBe("-214.6%");
    expect(formatPct(41.4)).toBe("41.4%");
  });

  it("兼容旧小数存储", () => {
    expect(formatPct(-2.146)).toBe("-214.6%");
    expect(formatPct(0.414)).toBe("41.4%");
  });
});

describe("formatTableCell percent strings", () => {
  it("带 % 的字符串直接引用", () => {
    expect(formatTableCell("经营CF增长率", "-214.6%")).toBe("-214.6%");
    expect(formatTableCell("同比", "+18.0%")).toBe("+18.0%");
    expect(formatTableCell("经营CF/净利", "41.4%")).toBe("41.4%");
  });

  it("占比列数值已是百分点", () => {
    expect(formatTableCell("占比", 5.0)).toBe("5%");
    expect(formatTableCell("占比", 5.1)).toBe("5.1%");
    expect(formatTableCell("占比", "4.9%")).toBe("4.9%");
    expect(formatTableCell("1年以上占比", 0.4)).toBe("0.4%");
    expect(formatTableCell("1年以上占比", "0.4%")).toBe("0.4%");
    expect(formatTableCell("收入占比", 0.7)).toBe("0.7%");
  });

  it("同比等列仍兼容旧小数比例", () => {
    expect(formatTableCell("同比", 0.494)).toBe("49.4%");
  });

  it("变更日列原样引用蓝本日期", () => {
    expect(formatTableCell("变更日", "2025/5/22")).toBe("2025/5/22");
    expect(formatTableCell("变更日", "2025/12/1")).toBe("2025/12/1");
    expect(formatTableCell("变更日", "2025年")).toBe("2025年");
  });

  it("非百分列数字串保留蓝本小数位", () => {
    expect(formatTableCell("营收(万)", "8.8")).toBe("8.8");
    expect(formatTableCell("权益乘数", "1.65x")).toBe("1.65x");
  });
});

describe("formatTableCellForRow wide metric tables", () => {
  const adRow = { 指标: "广告/销售费用" };
  const roiRow = { 指标: "综合ROI(营收/广告)" };

  it("蓝本含 % 时原样引用，不重算", () => {
    expect(formatTableCellForRow("可比公司A", "93.0%", adRow, "指标")).toBe("93.0%");
    expect(formatTableCellForRow("YYCQ", "64.1%", adRow, "指标")).toBe("64.1%");
    expect(formatTableCell("同比", "+18.0%")).toBe("+18.0%");
  });

  it("蓝本无 % 时仍按行指标推断为百分数", () => {
    expect(formatTableCellForRow("可比公司A", 93.0, adRow, "指标")).toBe("93%");
    expect(formatTableCellForRow("YYCQ", 64.1, adRow, "指标")).toBe("64.1%");
  });

  it("行指标为 ROI 时展示倍数", () => {
    expect(formatTableCellForRow("可比公司A", 2.2, roiRow, "指标")).toBe("2.2x");
    expect(formatTableCellForRow("YYCQ", "12.3x", roiRow, "指标")).toBe("12.3x");
  });
});

describe("formatDecimal2", () => {
  it("不补尾零", () => {
    expect(formatDecimal2(8.8)).toBe("8.8");
    expect(formatDecimal2(1.16)).toBe("1.16");
    expect(formatDecimal2(1234)).toBe("1,234");
  });
});

describe("formatPercentFromPoints", () => {
  it("整数不加小数", () => {
    expect(formatPercentFromPoints(100)).toBe("100%");
  });
});
