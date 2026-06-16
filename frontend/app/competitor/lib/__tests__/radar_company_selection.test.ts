import { isAllRadarCompaniesSelected, toggleRadarCompanySelection } from "../radar_company_selection";

const ALL = ["A", "B", "C"] as const;

describe("toggleRadarCompanySelection", () => {
  it("默认全选时首次点击为单选", () => {
    const selected = new Set(ALL);
    expect(toggleRadarCompanySelection(ALL, selected, "B")).toEqual(new Set(["B"]));
  });

  it("单选时再点同一项取消", () => {
    expect(toggleRadarCompanySelection(ALL, new Set(["B"]), "B")).toEqual(new Set());
  });

  it("单选时点其他项为多选", () => {
    expect(toggleRadarCompanySelection(ALL, new Set(["A"]), "C")).toEqual(new Set(["A", "C"]));
  });

  it("多选时可继续增减", () => {
    const mid = new Set(["A", "C"]);
    expect(toggleRadarCompanySelection(ALL, mid, "B")).toEqual(new Set(["A", "C", "B"]));
    expect(toggleRadarCompanySelection(ALL, mid, "A")).toEqual(new Set(["C"]));
  });
});

describe("isAllRadarCompaniesSelected", () => {
  it("识别全选", () => {
    expect(isAllRadarCompaniesSelected(ALL, new Set(ALL))).toBe(true);
    expect(isAllRadarCompaniesSelected(ALL, new Set(["A"]))).toBe(false);
  });
});
