import { FK } from "../field_keys";
import {
  SEC05_COST_SHARE,
  SEC05_MARGIN_CHANGE,
  SEC05_REV_DELTA_RATE,
  isSec05CompactHeader,
  normalizeSec05ProductRow,
  parseSec05MarginChangePct,
  sec05PercentPoints,
} from "../sec05_product";

const COMPACT_HEADERS = [
  "公司",
  "产品类型",
  "收入(万)",
  "收入占比",
  "成本(万)",
  "毛利率",
  "收入增减率",
  "毛利率变动",
];

describe("isSec05CompactHeader", () => {
  it("8 列紧凑表无成本占比", () => {
    expect(isSec05CompactHeader(COMPACT_HEADERS)).toBe(true);
  });

  it("12 列宽表含成本占比", () => {
    expect(isSec05CompactHeader([...COMPACT_HEADERS.slice(0, 5), "成本占比", "毛利率"])).toBe(false);
  });
});

describe("normalizeSec05ProductRow", () => {
  it("紧凑 8 列行保持不变", () => {
    const row = {
      公司: "三七互娱",
      产品类型: "移动游戏",
      "收入(万)": 1552908,
      收入占比: 97.3,
      "成本(万)": 366438,
      毛利率: 76.4,
      收入增减率: -8.0,
      毛利率变动: "-3.6pct",
    };
    const out = normalizeSec05ProductRow(row, COMPACT_HEADERS);
    expect(out[FK.grossMargin]).toBe(76.4);
    expect(out[SEC05_REV_DELTA_RATE]).toBe(-8.0);
    expect(out[SEC05_MARGIN_CHANGE]).toBe("-3.6pct");
  });

  it("完整 12 列行保持不变", () => {
    const row = {
      公司: "游艺春秋",
      产品类型: "移动游戏",
      "收入(万)": 14042,
      收入占比: 71.3,
      "成本(万)": 4776,
      成本占比: 68.6,
      毛利率: 66.0,
      收入增减额: "+477万",
      收入增减率: 3.5,
      成本增减额: "+317万",
      成本增减率: 7.1,
      毛利率变动: "-1.1pct",
    };
    expect(normalizeSec05ProductRow(row)[FK.grossMargin]).toBe(66.0);
    expect(normalizeSec05ProductRow(row)[SEC05_REV_DELTA_RATE]).toBe(3.5);
  });

  it("12 列压缩行：毛利率变动错位到收入增减额", () => {
    const row = {
      公司: "三七互娱",
      产品类型: "移动游戏",
      收入占比: 97.3,
      成本占比: 76.4,
      毛利率: -8.0,
      收入增减额: "-3.6pct",
    };
    const wideHeaders = [
      "公司",
      "产品类型",
      "收入(万)",
      "收入占比",
      "成本(万)",
      "成本占比",
      "毛利率",
      "收入增减额",
      "收入增减率",
      "成本增减额",
      "成本增减率",
      "毛利率变动",
    ];
    const out = normalizeSec05ProductRow(row, wideHeaders);
    expect(out[FK.grossMargin]).toBe(76.4);
    expect(out[SEC05_REV_DELTA_RATE]).toBe(-8.0);
    expect(out[SEC05_MARGIN_CHANGE]).toBe("-3.6pct");
  });

  it("压缩行：毛利率变动落在收入增减率列", () => {
    const row = {
      公司: "三七互娱",
      产品类型: "移动游戏",
      "收入(万)": 1552908,
      收入占比: 97.3,
      "成本(万)": 366438,
      [SEC05_COST_SHARE]: 76.4,
      [FK.grossMargin]: -8.0,
      [SEC05_REV_DELTA_RATE]: "-3.6pct",
    };
    const out = normalizeSec05ProductRow(row);
    expect(out[FK.grossMargin]).toBe(76.4);
    expect(out[SEC05_REV_DELTA_RATE]).toBe(-8.0);
    expect(out[SEC05_MARGIN_CHANGE]).toBe("-3.6pct");
  });

  it("压缩行：负毛利率", () => {
    const row = {
      公司: "掌趣科技",
      产品类型: "其他",
      [SEC05_COST_SHARE]: -16.5,
      [FK.grossMargin]: -3.4,
      [SEC05_REV_DELTA_RATE]: "-21.1pct",
    };
    const out = normalizeSec05ProductRow(row);
    expect(out[FK.grossMargin]).toBe(-16.5);
    expect(out[SEC05_REV_DELTA_RATE]).toBe(-3.4);
    expect(out[SEC05_MARGIN_CHANGE]).toBe("-21.1pct");
  });
});

describe("sec05PercentPoints", () => {
  it("0.7% 保持 0.7，不误乘 100", () => {
    expect(sec05PercentPoints(0.7)).toBe(0.7);
  });

  it("71.3% 保持 71.3", () => {
    expect(sec05PercentPoints(71.3)).toBe(71.3);
  });
});

describe("parseSec05MarginChangePct", () => {
  it("解析 pct 后缀", () => {
    expect(parseSec05MarginChangePct("-1.1pct")).toBe(-1.1);
    expect(parseSec05MarginChangePct("+2.3pct")).toBe(2.3);
  });
});
