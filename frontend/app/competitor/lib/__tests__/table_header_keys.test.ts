import {
  duplicateHeaderKey,
  pickChangeRateAfterDelta,
  resolveTableHeaderKeys,
} from "../table_header_keys";

describe("duplicateHeaderKey", () => {
  it("sec-03-1 两列变动率", () => {
    expect(duplicateHeaderKey("变动率", 1)).toBe("变动率");
    expect(duplicateHeaderKey("变动率", 2)).toBe("变动率__2");
  });
});

describe("pickChangeRateAfterDelta", () => {
  const headers = ["营收变动", "变动率", "净利变动", "变动率"];
  const headerKeys = resolveTableHeaderKeys(headers);

  it("按变动额列定位变动率", () => {
    const row = { 营收变动: -1, 变动率: "-8.46%", 净利变动: 1, 变动率__2: "+8.81%" };
    expect(pickChangeRateAfterDelta(row, "营收变动", headers)).toBe("-8.46%");
    expect(pickChangeRateAfterDelta(row, "净利变动", headers)).toBe("+8.81%");
  });

  it("旧 snapshot 单列时不把净利同比给营收", () => {
    const row = { 营收变动: -1, 变动率: "+8.81%", 净利变动: 1 };
    expect(pickChangeRateAfterDelta(row, "营收变动", headers, headerKeys)).toBeUndefined();
    expect(pickChangeRateAfterDelta(row, "净利变动", headers, headerKeys)).toBe("+8.81%");
  });
});

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
