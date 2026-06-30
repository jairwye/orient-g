/** 第 n 次出现的重复表头键（与 backend _header_cell_keys 一致；n 从 1 起） */
export function duplicateHeaderKey(label: string, occurrence = 1): string {
  return occurrence <= 1 ? label : `${label}__${occurrence}`;
}

const CHANGE_RATE = "变动率";
const CHANGE_RATE_RE = /^变动率(?:__\d+)?$/;

function changeRateKeysInRow(row: Record<string, unknown>): string[] {
  return Object.keys(row)
    .filter((k) => CHANGE_RATE_RE.test(k))
    .sort((a, b) => {
      const nA = a === CHANGE_RATE ? 1 : Number.parseInt(a.split("__")[1] ?? "1", 10);
      const nB = b === CHANGE_RATE ? 1 : Number.parseInt(b.split("__")[1] ?? "1", 10);
      return nA - nB;
    });
}

function isPresentCell(v: unknown): v is string | number {
  return v != null && v !== "" && v !== "—";
}

function effectiveHeaderKeys(headers: string[] | undefined, headerKeys?: string[]): string[] {
  if (headerKeys?.length) return headerKeys;
  if (headers?.length) return resolveTableHeaderKeys(headers);
  return [];
}

/** 变动额列后紧邻的「变动率」列键（sec-03-1：营收变动→变动率，净利变动→变动率__2） */
function changeRateKeyAfterDelta(keys: string[], deltaKey: string): string | undefined {
  const deltaIdx = keys.indexOf(deltaKey);
  if (deltaIdx < 0) return undefined;
  for (let i = deltaIdx + 1; i < keys.length; i++) {
    if (CHANGE_RATE_RE.test(keys[i])) return keys[i];
  }
  return undefined;
}

/**
 * 取「某变动额」列后紧邻的变动率单元格。
 * 兼容旧 snapshot：行内仅保留一个 `变动率` 键时（后列覆盖），只映射到第二列（净利），
 * 避免营收误读净利同比。
 */
export function pickChangeRateAfterDelta(
  row: Record<string, string | number | null | undefined>,
  deltaKey: string,
  headers?: string[],
  headerKeys?: string[],
): string | number | null | undefined {
  const keys = effectiveHeaderKeys(headers, headerKeys);
  const rateKey = changeRateKeyAfterDelta(keys, deltaKey);
  if (!rateKey) return undefined;

  const rateKeysInHeader = keys.filter((k) => CHANGE_RATE_RE.test(k));
  const rateKeysInRow = changeRateKeysInRow(row);
  const isLegacySingleRate =
    rateKeysInHeader.length >= 2 &&
    rateKeysInRow.length === 1 &&
    rateKeysInRow[0] === CHANGE_RATE;

  // 旧 snapshot 仅保留一个「变动率」键（后列覆盖）：该值为净利同比，不得用于营收
  if (isLegacySingleRate && rateKey === CHANGE_RATE) {
    return undefined;
  }

  const direct = row[rateKey];
  if (isPresentCell(direct)) return direct;

  if (isLegacySingleRate && rateKey !== CHANGE_RATE) {
    const legacy = row[CHANGE_RATE];
    if (isPresentCell(legacy)) return legacy;
  }

  return undefined;
}

/** @deprecated 用 pickChangeRateAfterDelta 按变动额列定位 */
export function pickRowChangeRate(
  row: Record<string, string | number | null | undefined>,
  headerKeys: string[] | undefined,
  occurrence: 1 | 2,
): string | number | null | undefined {
  const deltaKey = occurrence === 1 ? "营收变动" : "净利变动";
  return pickChangeRateAfterDelta(row, deltaKey, undefined, headerKeys);
}

/** 重复表头列 → 唯一 row 键（与 backend _header_cell_keys 一致） */
export function resolveTableHeaderKeys(headers: string[], headerKeys?: string[]): string[] {
  if (headerKeys?.length === headers.length) return headerKeys;
  const seen = new Map<string, number>();
  return headers.map((h) => {
    const n = seen.get(h) ?? 0;
    seen.set(h, n + 1);
    return n === 0 ? h : `${h}__${n + 1}`;
  });
}
