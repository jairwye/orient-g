import type { CompetitorReportSnapshot } from "../types";
import {
  colToLabel,
  companyColsForSnapshot,
  companyColsFromTableHeaders,
  companyDisplayLabel,
  isLikelyMetricHeader,
  isWideCompanyTable,
  labelToCol,
  normalizeTableCompanyKeys,
  rowValueForCompany,
  subjectUiLabel,
  SUBJECT_COL,
} from "../companies";

const snapSubjectLabel = {
  companies: [{ id: "yycq", label: "本公司", short: "YYCQ" }],
} as CompetitorReportSnapshot;

const snapYycqShort = {
  companies: [{ id: "yycq", label: "YYCQ", short: "YYCQ" }],
} as CompetitorReportSnapshot;

/** 模拟内网蓝本：宽表第一列用历史列名（非 canonical「本公司」） */
const snapLegacySubjectHeader = {
  companies: [{ id: "yycq", label: "本公司", short: "YYCQ" }],
  sections: [
    {
      id: "sec-04",
      blocks: [
        {
          kind: "table",
          anchor: "sec-04-1",
          headers: ["指标", "主体列A", "可比公司B"],
          rows: [],
        },
      ],
    },
  ],
} as CompetitorReportSnapshot;

describe("companyDisplayLabel", () => {
  it("匿名蓝本 snapshot.label=本公司 时页面展示 YYCQ", () => {
    expect(companyDisplayLabel("YYCQ", snapSubjectLabel)).toBe("YYCQ");
    expect(companyDisplayLabel("本公司", snapSubjectLabel)).toBe("YYCQ");
    expect(colToLabel("本公司", snapSubjectLabel)).toBe("YYCQ");
    expect(subjectUiLabel(snapSubjectLabel)).toBe("YYCQ");
  });

  it("snapshot.label 为 YYCQ 时页面展示 YYCQ", () => {
    expect(companyDisplayLabel("YYCQ", snapYycqShort)).toBe("YYCQ");
    expect(companyDisplayLabel("本公司", snapYycqShort)).toBe("YYCQ");
  });

  it("蓝本历史列名原样展示", () => {
    const snap = {
      companies: [{ id: "yycq", label: "历史列名A", short: "YYCQ" }],
    } as CompetitorReportSnapshot;
    expect(companyDisplayLabel("历史列名A", snap)).toBe("历史列名A");
  });

  it("蓝本宽表第一列为历史列名时页面展示该列名", () => {
    expect(companyDisplayLabel("本公司", snapLegacySubjectHeader)).toBe("主体列A");
    expect(subjectUiLabel(snapLegacySubjectHeader)).toBe("主体列A");
  });

  it("无 snapshot 时主体默认 YYCQ", () => {
    expect(companyDisplayLabel("本公司")).toBe("YYCQ");
    expect(companyDisplayLabel("YYCQ")).toBe("YYCQ");
  });
});

describe("companyColsForSnapshot", () => {
  const snap = {
    companies: [
      { id: "yycq", label: "YYCQ" },
      { id: "37", label: "可比公司A" },
    ],
  } as CompetitorReportSnapshot;

  it("优先用宽表表头中的公司列", () => {
    expect(companyColsForSnapshot(snap, ["指标", "YYCQ", "可比公司A"])).toEqual([
      "YYCQ",
      "可比公司A",
    ]);
  });

  it("长表（公司×指标）不把 营收(亿) 当成公司列", () => {
    const kpiHeaders = ["公司", "营收(亿)", "营收同比", "净利(亿)"];
    expect(isWideCompanyTable(kpiHeaders)).toBe(false);
    expect(companyColsFromTableHeaders(kpiHeaders)).toEqual([]);
    expect(isLikelyMetricHeader("营收(亿)")).toBe(true);
  });

  it("无表头时回退 snapshot.companies", () => {
    expect(companyColsForSnapshot(snap)).toEqual(["YYCQ", "可比公司A"]);
  });
});

/** 模拟错误 snapshot：companies 被长表列序误映射为指标名 */
const snapBrokenCompanyMeta = {
  companies: [
    { id: "yycq", label: "营收(亿)", short: "YYCQ" },
    { id: "37", label: "营收同比", short: "可比公司A" },
    { id: "wm", label: "净利(亿)", short: "可比公司B" },
  ],
  sections: [
    {
      id: "sec-04",
      blocks: [
        {
          kind: "table",
          anchor: "sec-04-1",
          headers: ["指标", "YYCQ", "可比公司A", "可比公司B"],
          rows: [],
        },
      ],
    },
  ],
} as CompetitorReportSnapshot;

describe("broken snapshot company labels", () => {
  it("主体展示名来自宽表 YYCQ，而非 营收(亿)", () => {
    expect(subjectUiLabel(snapBrokenCompanyMeta)).toBe("YYCQ");
    expect(colToLabel("本公司", snapBrokenCompanyMeta)).toBe("YYCQ");
    expect(colToLabel("YYCQ", snapBrokenCompanyMeta)).toBe("YYCQ");
  });

  it("宽表扫描优先于错误的 companies.label", () => {
    expect(companyColsForSnapshot(snapBrokenCompanyMeta)).toEqual([
      "YYCQ",
      "可比公司A",
      "可比公司B",
    ]);
  });
});

describe("rowValueForCompany", () => {
  it("历史主体列名与 YYCQ / 本公司 等价", () => {
    const row = { 指标: "人均创收(万)", 主体列A: 73.9, 可比公司B: 500 };
    expect(rowValueForCompany(row, "YYCQ", snapLegacySubjectHeader)).toBe(73.9);
    expect(rowValueForCompany(row, "本公司", snapLegacySubjectHeader)).toBe(73.9);
    expect(rowValueForCompany(row, "可比公司B", snapLegacySubjectHeader)).toBe(500);
  });
});

describe("normalizeTableCompanyKeys", () => {
  it("保留蓝本表头原文", () => {
    const table = {
      kind: "table" as const,
      anchor: "sec-04-1",
      headers: ["指标", "本公司", "可比公司A"],
      rows: [{ 指标: "人数", 本公司: 100, 可比公司A: 200 }],
    };
    const out = normalizeTableCompanyKeys(table);
    expect(out.headers).toEqual(["指标", "本公司", "可比公司A"]);
    expect(out.rows[0]?.["本公司"]).toBe(100);
    expect(labelToCol(out.headers[1]!)).toBe(SUBJECT_COL);
  });
});
