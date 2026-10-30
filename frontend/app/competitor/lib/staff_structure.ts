import { FK } from "./field_keys";
import { parseNum } from "./format";

export type StaffBucket = "rd" | "ops" | "adm";

/** 行政财务 ← 列名「行政财务」，2026-h1 蓝本列名「其他」 */
const BUCKET_KEYS: Record<StaffBucket, readonly string[]> = {
  rd: [FK.rdStaff],
  ops: [FK.opsSales],
  adm: [FK.adminFinance, FK.staffOther],
};

function bucketCount(
  row: Record<string, string | number | null | undefined>,
  keys: readonly string[],
): number {
  for (const key of keys) {
    if (!Object.prototype.hasOwnProperty.call(row, key)) continue;
    const raw = row[key];
    if (raw == null || raw === "") continue;
    const n = parseNum(raw);
    if (n != null) return n;
  }
  return 0;
}

/** 人员结构三桶人数。行政财务优先，缺列时用「其他」。不读研发占比。 */
export function staffBucketCount(
  row: Record<string, string | number | null | undefined>,
  bucket: StaffBucket,
): number {
  return bucketCount(row, BUCKET_KEYS[bucket]);
}

export function staffStructureShares(
  row: Record<string, string | number | null | undefined>,
): { rd: number; ops: number; adm: number } | null {
  const rd = staffBucketCount(row, "rd");
  const ops = staffBucketCount(row, "ops");
  const adm = staffBucketCount(row, "adm");
  const total = rd + ops + adm;
  if (total <= 0) return null;
  return {
    rd: (rd / total) * 100,
    ops: (ops / total) * 100,
    adm: (adm / total) * 100,
  };
}
