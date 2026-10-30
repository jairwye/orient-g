import { splitSummaryDetailTables } from "../selectors";
import type { TableBlock } from "../types";

function table(headers: string[], rows: TableBlock["rows"] = [{ a: 1 }]): TableBlock {
  return { kind: "table", anchor: "sec-09-7", headers, rows };
}

describe("splitSummaryDetailTables", () => {
  const summary = table(["科目", "YYCQ", "可比公司A"], [{ 科目: "合计(万)", YYCQ: 1, 可比公司A: 2 }]);
  const detail = table(
    ["公司", "产品", "金额(万)"],
    [{ 公司: "可比公司A", 产品: "理财A", "金额(万)": 10 }],
  );

  it("只有宽表时不返回明细", () => {
    expect(splitSummaryDetailTables([summary])).toEqual({ summary });
  });

  it("宽表 + 长表时拆成汇总与明细", () => {
    expect(splitSummaryDetailTables([summary, detail])).toEqual({ summary, detail });
    expect(splitSummaryDetailTables([detail, summary])).toEqual({ summary, detail });
  });

  it("只有公司长表时当作明细", () => {
    expect(splitSummaryDetailTables([detail])).toEqual({ detail });
  });

  it("只有竞企名称长表时当作明细", () => {
    const peerDetail = table(
      ["竞企名称", "一级科目", "金额(万)"],
      [{ 竞企名称: "可比公司B", 一级科目: "交易性金融资产", "金额(万)": 8603 }],
    );
    expect(splitSummaryDetailTables([peerDetail])).toEqual({ detail: peerDetail });
  });

  it("科目列不是精确「科目」时仍把竞企长表拆成明细", () => {
    const subjectSummary = table(
      ["二级科目(万)", "YYCQ", "可比公司A"],
      [{ "二级科目(万)": "交易性金融资产", YYCQ: 9347, 可比公司A: 292853 }],
    );
    const peerDetail = table(
      ["竞企名称", "金额(万)"],
      [
        { 竞企名称: "可比公司B", "金额(万)": 8603 },
        { 竞企名称: null, "金额(万)": 16 },
      ],
    );
    expect(splitSummaryDetailTables([subjectSummary, peerDetail])).toEqual({
      summary: subjectSummary,
      detail: peerDetail,
    });
    expect(splitSummaryDetailTables([peerDetail, subjectSummary])).toEqual({
      summary: subjectSummary,
      detail: peerDetail,
    });
  });
});
