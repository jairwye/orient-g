import { resolveTableHeaderKeys } from "../table_header_keys";

describe("resolveTableHeaderKeys", () => {
  it("重复表头生成唯一键", () => {
    const headers = ["产品分类", "占比（%）", "占比（%）", "同比变化（%）"];
    expect(resolveTableHeaderKeys(headers)).toEqual([
      "产品分类",
      "占比（%）",
      "占比（%）__2",
      "同比变化（%）",
    ]);
  });

  it("优先使用 snapshot header_keys", () => {
    const keys = ["a", "b__2"];
    expect(resolveTableHeaderKeys(["a", "b"], keys)).toBe(keys);
  });
});
