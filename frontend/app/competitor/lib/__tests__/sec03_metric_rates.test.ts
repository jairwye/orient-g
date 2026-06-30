import { buildMetricDelta } from "../metric_delta";
import { duplicateHeaderKey, pickChangeRateAfterDelta } from "../table_header_keys";

const SEC03_HEADERS = [
  "公司",
  "营收(万)",
  "营收变动",
  "变动率",
  "净利(万)",
  "净利变动",
  "变动率",
  "ROE",
  "ROE变动",
];

const SEC03_HEADER_KEYS = [
  "公司",
  "营收(万)",
  "营收变动",
  "变动率",
  "净利(万)",
  "净利变动",
  "变动率__2",
  "ROE",
  "ROE变动",
];

/** sec-03-1 样例行（数值与 uploads 蓝本一致，公司名为占位） */
const sampleRow = {
  公司: "可比公司A",
  "营收(万)": 1596571,
  营收变动: -147525,
  变动率: "-8.46%",
  "净利(万)": 289895,
  净利变动: 23465,
  [duplicateHeaderKey("变动率", 2)]: "+8.81%",
};

/** 旧 snapshot：行内仅一个「变动率」，值为净利同比 */
const legacyRow = {
  公司: "可比公司A",
  "营收(万)": 1596571,
  营收变动: -147525,
  变动率: "+8.81%",
  "净利(万)": 289895,
  净利变动: 23465,
};

describe("sec-03-1 变动率列", () => {
  it("完整 snapshot：营收/净利各引用紧邻变动率列", () => {
    expect(pickChangeRateAfterDelta(sampleRow, "营收变动", SEC03_HEADERS, SEC03_HEADER_KEYS)).toBe(
      "-8.46%",
    );
    expect(pickChangeRateAfterDelta(sampleRow, "净利变动", SEC03_HEADERS, SEC03_HEADER_KEYS)).toBe(
      "+8.81%",
    );

    const revenueDelta = buildMetricDelta(
      sampleRow.营收变动,
      pickChangeRateAfterDelta(sampleRow, "营收变动", SEC03_HEADERS, SEC03_HEADER_KEYS),
    );
    const profitDelta = buildMetricDelta(
      sampleRow.净利变动,
      pickChangeRateAfterDelta(sampleRow, "净利变动", SEC03_HEADERS, SEC03_HEADER_KEYS),
    );

    expect(revenueDelta.rateText).toMatch(/8\.46/);
    expect(profitDelta.rateText).toBe("+8.81%");
  });

  it("旧 snapshot 单列：营收不显示错误同比，净利仍可读", () => {
    expect(
      pickChangeRateAfterDelta(legacyRow, "营收变动", SEC03_HEADERS, SEC03_HEADER_KEYS),
    ).toBeUndefined();
    expect(pickChangeRateAfterDelta(legacyRow, "净利变动", SEC03_HEADERS, SEC03_HEADER_KEYS)).toBe(
      "+8.81%",
    );

    const revenueDelta = buildMetricDelta(
      legacyRow.营收变动,
      pickChangeRateAfterDelta(legacyRow, "营收变动", SEC03_HEADERS, SEC03_HEADER_KEYS),
    );
    const profitDelta = buildMetricDelta(
      legacyRow.净利变动,
      pickChangeRateAfterDelta(legacyRow, "净利变动", SEC03_HEADERS, SEC03_HEADER_KEYS),
    );

    expect(revenueDelta.rateText).toBeNull();
    expect(profitDelta.rateText).toBe("+8.81%");
  });
});
