import {
  assetAmountToYi,
  assetRowValue,
  buildCashDebtChartRows,
  normalizeAssetSubjectLabel,
  scoreAssetSubjectMatch,
} from "../asset_cash_debt";
import type { CompetitorReportSnapshot } from "../types";

const snap = {
  companies: [
    { id: "yycq", label: "本公司", short: "YYCQ" },
    { id: "a", label: "可比公司A" },
  ],
} as CompetitorReportSnapshot;

describe("normalizeAssetSubjectLabel / scoreAssetSubjectMatch", () => {
  it("去掉行尾单位后缀后可精确匹配", () => {
    expect(normalizeAssetSubjectLabel("货币资金(万)")).toBe("货币资金");
    expect(normalizeAssetSubjectLabel("货币资金（亿）")).toBe("货币资金");
    expect(scoreAssetSubjectMatch("货币资金(万)", "货币资金")).toBe(3);
    expect(scoreAssetSubjectMatch("货币资金", "货币资金")).toBe(3);
  });

  it("其他货币资金不得命中货币资金", () => {
    expect(scoreAssetSubjectMatch("其他货币资金", "货币资金")).toBe(0);
    expect(scoreAssetSubjectMatch("货币资金及其他", "货币资金")).toBe(2);
  });
});

describe("assetAmountToYi", () => {
  it("默认按万元换算为亿", () => {
    expect(assetAmountToYi(15750, "货币资金")).toBeCloseTo(1.575);
    expect(assetAmountToYi(8000, "科目(万)表头下的短期借款")).toBeCloseTo(0.8);
  });

  it("行名含亿时不换算", () => {
    expect(assetAmountToYi(1.58, "货币资金(亿)")).toBeCloseTo(1.58);
    expect(assetAmountToYi(0.8, "短期借款（亿）")).toBeCloseTo(0.8);
  });
});

describe("assetRowValue", () => {
  it("科目(万) 表头下按精确科目取数，避开其他货币资金", () => {
    const table = {
      headers: ["科目(万)", "本公司", "可比公司A"],
      rows: [
        { "科目(万)": "其他货币资金", 本公司: 999, 可比公司A: 100 },
        { "科目(万)": "货币资金", 本公司: 15750, 可比公司A: 22000 },
        { "科目(万)": "短期借款", 本公司: 8000, 可比公司A: 5000 },
      ],
    };
    expect(assetRowValue(table, "货币资金", "本公司", snap)).toEqual({
      value: 15750,
      label: "货币资金",
    });
    expect(assetRowValue(table, "短期借款", "本公司", snap)).toEqual({
      value: 8000,
      label: "短期借款",
    });
  });

  it("行名自带(万)时仍可匹配", () => {
    const table = {
      headers: ["科目", "YYCQ"],
      rows: [{ 科目: "货币资金(万)", YYCQ: 8527 }],
    };
    expect(assetRowValue(table, "货币资金", "YYCQ", snap)?.value).toBe(8527);
  });

  it("缺行返回 null", () => {
    const table = {
      headers: ["科目(万)", "本公司"],
      rows: [{ "科目(万)": "应收账款", 本公司: 1 }],
    };
    expect(assetRowValue(table, "货币资金", "本公司", snap)).toBeNull();
  });
});

describe("buildCashDebtChartRows", () => {
  it("万→亿并按现金降序；缺表时空数组", () => {
    const table = {
      headers: ["科目(万)", "本公司", "可比公司A"],
      rows: [
        { "科目(万)": "其他货币资金", 本公司: 1, 可比公司A: 1 },
        { "科目(万)": "货币资金", 本公司: 10000, 可比公司A: 30000 },
        { "科目(万)": "短期借款", 本公司: 5000, 可比公司A: 1000 },
      ],
    };
    expect(
      buildCashDebtChartRows(table, ["本公司", "可比公司A"], snap, (c) => c),
    ).toEqual([
      { name: "可比公司A", cash: 3, debt: 0.1 },
      { name: "本公司", cash: 1, debt: 0.5 },
    ]);
    expect(buildCashDebtChartRows(null, ["本公司"], snap, (c) => c)).toEqual([]);
  });
});
