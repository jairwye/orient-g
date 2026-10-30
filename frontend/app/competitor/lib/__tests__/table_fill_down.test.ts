import { companyFillDownKey, fillDownTableRows } from "../table_fill_down";

describe("companyFillDownKey", () => {
  it("识别竞企名称，而不是只认「公司」", () => {
    expect(companyFillDownKey(["竞企名称", "一级科目", "金额(万)"])).toBe("竞企名称");
    expect(companyFillDownKey(["公司", "金额(万)"])).toBe("公司");
    expect(companyFillDownKey(["公司名称", "金额(万)"])).toBe("公司名称");
    expect(companyFillDownKey(["二级科目(万)", "YYCQ", "可比公司A"])).toBeUndefined();
  });
});

describe("fillDownTableRows", () => {
  it("投资理财明细：合并单元格的竞企名称向下填充", () => {
    const rows = fillDownTableRows(
      [
        { 竞企名称: "可比公司B", 一级科目: "交易性金融资产", "金额(万)": 8603.14 },
        { 竞企名称: null, 一级科目: "交易性金融资产", "金额(万)": 15.76 },
        { 竞企名称: "—", 一级科目: "其他权益工具投资", "金额(万)": 4839.46 },
        { 竞企名称: "可比公司A", 一级科目: "交易性金融资产", "金额(万)": 266907.42 },
        { 竞企名称: "", 一级科目: "其他非流动资产", "金额(万)": 246061.22 },
      ],
      ["竞企名称", "一级科目", "金额(万)"],
    );

    expect(rows.map((row) => row["竞企名称"])).toEqual([
      "可比公司B",
      "可比公司B",
      "可比公司B",
      "可比公司A",
      "可比公司A",
    ]);
  });

  it("前面没有竞企名称时保留空值", () => {
    const rows = fillDownTableRows(
      [{ 竞企名称: null, "金额(万)": 1 }],
      ["竞企名称", "金额(万)"],
    );
    expect(rows[0]?.["竞企名称"]).toBe("");
  });
});
