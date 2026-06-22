import { FK } from "../field_keys";
import { SUBJECT_COL } from "../companies";
import {
  formatLaborCostDataValue,
  getLaborCostCellValue,
  isLaborCostSectionRow,
  laborCostTableHasFullSections,
} from "../labor_cost_table_utils";

const headers = ["指标", "本公司", "可比公司A"];

describe("isLaborCostSectionRow", () => {
  it("识别 **人力成本** 分组行", () => {
    expect(
      isLaborCostSectionRow(
        { 指标: "**人力成本**", 本公司: null, 可比公司A: null },
        headers,
        FK.metric,
      ),
    ).toBe(true);
  });

  it("识别无 ** 的职工福利分组行", () => {
    expect(
      isLaborCostSectionRow(
        { 指标: "职工福利", 本公司: null, 可比公司A: null },
        headers,
        FK.metric,
      ),
    ).toBe(true);
  });

  it("普通指标行不是分组行", () => {
    expect(
      isLaborCostSectionRow(
        { 指标: "月均(万)", 本公司: null, 可比公司A: 12658 },
        headers,
        FK.metric,
      ),
    ).toBe(false);
  });
});

describe("formatLaborCostDataValue", () => {
  it("空值显示 —", () => {
    expect(formatLaborCostDataValue("月均(万)", null)).toBe("—");
  });

  it("增减变动带正号", () => {
    expect(formatLaborCostDataValue("月均增减变动(万)", 22)).toBe("+22");
    expect(formatLaborCostDataValue("人均增减变动(万/年)", 0.2)).toBe("+0.2");
  });

  it("人均(元/年)千分位", () => {
    expect(formatLaborCostDataValue("人均(元/年)", 18180)).toBe("18,180");
  });

  it("零值显示 0", () => {
    expect(formatLaborCostDataValue("月均(万)", 0)).toBe("0");
  });
});

describe("laborCostTableHasFullSections", () => {
  it("完整蓝本含职工福利与工会经费", () => {
    const rows = [
      { 指标: "**人力成本**" },
      { 指标: "月均(万)" },
      { 指标: "**职工福利**" },
      { 指标: "人均(元/年)", 可比公司A: 18180 },
      { 指标: "**工会经费及教育经费**" },
      { 指标: "人均(元/年)", 可比公司A: 1200 },
    ];
    expect(laborCostTableHasFullSections(rows)).toBe(true);
  });

  it("旧版扁平表不含分组", () => {
    expect(
      laborCostTableHasFullSections([
        { 指标: "月均(万)" },
        { 指标: "人均(万/年)" },
      ]),
    ).toBe(false);
  });
});

describe("getLaborCostCellValue", () => {
  it("本公司与 YYCQ 列等价", () => {
    const row = { 指标: "月均(万)", YYCQ: null, 可比公司A: 100 };
    expect(getLaborCostCellValue(row, "YYCQ")).toBeNull();
    expect(getLaborCostCellValue(row, SUBJECT_COL)).toBeNull();
    expect(getLaborCostCellValue(row, "可比公司A")).toBe(100);
  });
});
