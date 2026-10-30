import { FK } from "../field_keys";
import { staffBucketCount, staffStructureShares } from "../staff_structure";

describe("staff structure buckets", () => {
  it("「其他」计入行政财务，研发占比不参与人数", () => {
    const row = {
      [FK.company]: "YYCQ",
      [FK.rdStaff]: 52,
      [FK.rdShare]: "25.5%",
      [FK.opsSales]: 114,
      [FK.staffOther]: 38,
    };
    expect(staffBucketCount(row, "rd")).toBe(52);
    expect(staffBucketCount(row, "ops")).toBe(114);
    expect(staffBucketCount(row, "adm")).toBe(38);
    const shares = staffStructureShares(row);
    expect(shares).not.toBeNull();
    expect(shares!.rd + shares!.ops + shares!.adm).toBeCloseTo(100, 5);
    expect(shares!.adm).toBeCloseTo((38 / 204) * 100, 5);
  });

  it("已有行政财务列时优先该列，空值才回退到其他", () => {
    expect(
      staffBucketCount(
        { [FK.adminFinance]: 12, [FK.staffOther]: 99, [FK.rdStaff]: 1, [FK.opsSales]: 1 },
        "adm",
      ),
    ).toBe(12);
    expect(
      staffBucketCount({ [FK.adminFinance]: null, [FK.staffOther]: 7 }, "adm"),
    ).toBe(7);
  });

  it("三桶都空时不画", () => {
    expect(staffStructureShares({ [FK.company]: "YYCQ", [FK.rdStaff]: null, [FK.adminFinance]: null })).toBeNull();
  });
});
