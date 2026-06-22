/**
 * 竞品财报 — 财务分析视角（同业基准、驱动归因、质量分级）
 * 纯函数，从 snapshot 表推导可扫读的分析师结论。
 */
import { SUBJECT_COL, colToLabel, companyColsForSnapshot, rowValueForCompany } from "./companies";
import { FK, FK_AMOUNT_CHANGE, FK_CF_ITEM, FK_CHANGE, FK_METRIC, CL } from "./field_keys";
import { cfProfitRatioToPercentPoints, parseNum, round2, toPercentPoints } from "./format";
import { getTable } from "./selectors";
import type { CompetitorReportSnapshot, TableBlock } from "./types";

export type InsightTone = "positive" | "warning" | "negative" | "neutral";

export type AnalystInsight = {
  label: string;
  headline: string;
  detail?: string;
  tone: InsightTone;
};

export type DupontPoint = {
  colKey: string;
  name: string;
  roe: number;
  netMargin: number;
  turnover: number;
  leverage: number;
  driver: "margin" | "turnover" | "leverage";
  driverLabel: string;
};

export type CashQualityTier = "A" | "B" | "C" | "D";

export type CashQualityPoint = {
  colKey: string;
  name: string;
  profit: number;
  ocf: number;
  ratioPct: number;
  tier: CashQualityTier;
  tierLabel: string;
};

export type AcquisitionModel = "buy" | "brand" | "channel" | "organic";

function tableMetric(table: TableBlock | undefined, metric: string, col: string): number | null {
  const row = table?.rows.find((r) => String(r[FK.metric] ?? "") === metric);
  if (!row) return null;
  return parseNum(rowValueForCompany(row, col));
}

function cellNum(row: Record<string, string | number | null | undefined> | undefined, col: string): number | null {
  return parseNum(rowValueForCompany(row, col));
}


export function peerMedian(values: number[]): number | null {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid]! : round2((sorted[mid - 1]! + sorted[mid]!) / 2);
}

function companyName(col: string, snapshot?: CompetitorReportSnapshot): string {
  return colToLabel(col, snapshot);
}

function driverLabel(d: DupontPoint["driver"]): string {
  if (d === "margin") return "\u51c0\u5229\u7387\u9a71\u52a8";
  if (d === "turnover") return "\u8d44\u4ea7\u5468\u8f6c\u9a71\u52a8";
  return "\u6760\u6746\u9a71\u52a8";
}

export function parseDupontPoints(snapshot: CompetitorReportSnapshot): DupontPoint[] {
  const dupont = getTable(snapshot, "sec-06-4");
  if (!dupont?.rows.length) return [];

  const raw = dupont.rows
    .map((row) => {
      const colKey = String(row[FK.company] ?? "");
      const roeRaw = parseNum(row["ROE"]);
      const marginRaw = parseNum(row["\u51c0\u5229\u7387"]);
      const turnover = parseNum(row["\u603b\u8d44\u4ea7\u5468\u8f6c\u7387"]);
      const leverage = parseNum(row["\u6743\u76ca\u4e58\u6570"]);
      if (!colKey || roeRaw == null || marginRaw == null || turnover == null || leverage == null) return null;
      return {
        colKey,
        name: companyName(colKey),
        roe: toPercentPoints(roeRaw),
        netMargin: toPercentPoints(marginRaw),
        turnover,
        leverage,
      };
    })
    .filter(Boolean) as Omit<DupontPoint, "driver" | "driverLabel">[];

  const medMargin = peerMedian(raw.map((r) => r.netMargin)) ?? 1;
  const medTurn = peerMedian(raw.map((r) => r.turnover)) ?? 1;
  const medLev = peerMedian(raw.map((r) => r.leverage)) ?? 1;

  return raw.map((r) => {
    const scores = {
      margin: medMargin > 0 ? r.netMargin / medMargin : 0,
      turnover: medTurn > 0 ? r.turnover / medTurn : 0,
      leverage: medLev > 0 ? r.leverage / medLev : 0,
    };
    const driver = (Object.entries(scores).sort((a, b) => b[1] - a[1])[0]?.[0] ??
      "margin") as DupontPoint["driver"];
    return { ...r, driver, driverLabel: driverLabel(driver) };
  });
}

export function classifyCashQuality(profit: number, ocf: number, ratioPct: number): { tier: CashQualityTier; tierLabel: string } {
  if (profit < 0 && ocf < 0) return { tier: "D", tierLabel: "\u53cc\u8d1f\u2014\u4e3b\u8425\u6536\u5165\u8840\u4e0d\u8db3" };
  if (profit > 0 && ocf < 0) return { tier: "D", tierLabel: "\u865a\u76c8\u2014\u5229\u6da6\u65e0\u73b0\u91d1\u652f\u6491" };
  if (profit < 0 && ocf >= 0) return { tier: "B", tierLabel: "\u51cf\u503c\u51b2\u51fb\u2014\u6392\u9664\u540e\u4ecd\u6709\u9020\u8840" };
  if (ratioPct >= 120) return { tier: "A", tierLabel: "\u9ad8\u542b\u91d1\u91cf\u2014\u73b0\u91d1\u5f3a\u4e8e\u5229\u6da6" };
  if (ratioPct >= 80) return { tier: "B", tierLabel: "\u57fa\u672c\u5339\u914d\u2014\u5229\u6da6\u53ef\u5151\u73b0" };
  if (ratioPct >= 50) return { tier: "C", tierLabel: "\u504f\u5f31\u2014\u975e\u73b0\u91d1\u9879\u5360\u6bd4\u504f\u9ad8" };
  return { tier: "C", tierLabel: "\u504f\u5f31\u2014\u73b0\u91d1\u6536\u655b\u4e0d\u8db3" };
}

export function parseCashQualityPoints(snapshot: CompetitorReportSnapshot): CashQualityPoint[] {
  const cf = getTable(snapshot, "sec-08-2");
  if (!cf) return [];
  const profitRow = cf.rows.find((r) => String(r[FK.metric] ?? "").includes("\u51c0\u5229\u6da6"));
  const ocfRow = cf.rows.find((r) => /经营.*(CF|现金流)/.test(String(r[FK.metric] ?? "")));
  const ratioRow = cf.rows.find((r) => /经营.*(CF|现金流)\/净利/.test(String(r[FK.metric] ?? "")));

  return companyColsForSnapshot(snapshot).map((col) => {
    const profit = profitRow ? parseNum(rowValueForCompany(profitRow, col)) : null;
    const ocf = ocfRow ? parseNum(rowValueForCompany(ocfRow, col)) : null;
    if (profit == null && ocf == null) return null;
    const p = profit ?? 0;
    const o = ocf ?? 0;
    let ratioPct = 0;
    if (ratioRow) {
      const raw = parseNum(rowValueForCompany(ratioRow, col));
      if (raw != null) ratioPct = cfProfitRatioToPercentPoints(raw);
    } else if (p !== 0) {
      ratioPct = (o / p) * 100;
    }
    const { tier, tierLabel } = classifyCashQuality(p, o, ratioPct);
    return { colKey: col, name: companyName(col, snapshot), profit: p, ocf: o, ratioPct, tier, tierLabel };
  }).filter(Boolean) as CashQualityPoint[];
}

export function deriveBalanceInsights(snapshot: CompetitorReportSnapshot): AnalystInsight[] {
  const dupont = parseDupontPoints(snapshot);
  const insights: AnalystInsight[] = [];

  if (dupont.length) {
    const top = [...dupont].sort((a, b) => b.roe - a.roe)[0]!;
    insights.push({
      label: "ROE \u6392\u540d",
      headline: `${top.name} ROE ${top.roe.toFixed(1)}% \u4e3a\u516b\u5bb6\u6700\u9ad8`,
      detail: `\u4e3b\u8981\u7531${top.driverLabel}\u62c9\u52a8\uff08\u51c0\u5229\u7387 ${top.netMargin.toFixed(1)}%\u3001\u5468\u8f6c ${top.turnover.toFixed(2)}x\u3001\u6743\u76ca\u4e58\u6570 ${top.leverage.toFixed(2)}x\uff09`,
      tone: top.roe >= 15 ? "positive" : "neutral",
    });
    const negative = dupont.filter((d) => d.roe < 0);
    if (negative.length) {
      const worst = negative.sort((a, b) => a.roe - b.roe)[0]!;
      insights.push({
        label: "\u4e8f\u635f\u89e3\u6784",
        headline: `${worst.name} ROE ${worst.roe.toFixed(1)}%\uff0c\u6839\u5728\u51c0\u5229\u7387 ${worst.netMargin.toFixed(1)}%`,
        detail:
          worst.turnover < 0.3
            ? `\u8d44\u4ea7\u5468\u8f6c\u4ec5 ${worst.turnover.toFixed(2)}x\uff0c\u5927\u91cf\u8d44\u4ea7\u672a\u8f6c\u5316\u4e3a\u6536\u5165`
            : `\u9700\u5173\u6ce8\u8d39\u7528\u7ed3\u6784\u4e0e\u4e00\u6b21\u6027\u79d1\u76ee\u5bf9 ROE \u7684\u62d6\u7d2f`,
        tone: "negative",
      });
    }
    const implied = impliedDupontRoe(top.netMargin, top.turnover, top.leverage);
    if (Math.abs(implied - top.roe) < 3) {
      insights.push({
        label: CL.dupontBridge,
        headline: `${top.name} ROE ${top.roe.toFixed(1)}% \u2248 ${top.netMargin.toFixed(1)}% \u00d7 ${top.turnover.toFixed(2)}x \u00d7 ${top.leverage.toFixed(2)}x`,
        detail: `\u9a8c\u7b97\u503c ${implied.toFixed(1)}%\uff0c\u4e09\u56e0\u5b50\u53ef\u95ed\u73af\u2014\u9a71\u52a8\u4e3b\u56e0\u4e3a${top.driverLabel}`,
        tone: "positive",
      });
    }
  }

  return insights.slice(0, 3);
}

/** 杜邦验算：净利率(%) × 周转 × 权益乘数 → 隐含 ROE(%) */
export function impliedDupontRoe(marginPct: number, turnover: number, leverage: number): number {
  return (marginPct / 100) * turnover * leverage * 100;
}

function changeRow(table: TableBlock | undefined, label: string) {
  return table?.rows.find((r) => String(r[FK_CHANGE] ?? r[FK.subject] ?? "") === label);
}

function assetRow(table: TableBlock | undefined, label: string) {
  return table?.rows.find((r) => String(r[FK.subject] ?? "").startsWith(label));
}

/** sec-06-1：期末科目结构（FP&A） */
export function deriveAssetFpaInsights(snapshot: CompetitorReportSnapshot): AnalystInsight[] {
  const assets = getTable(snapshot, "sec-06-1");
  const insights: AnalystInsight[] = [];
  if (!assets?.rows.length) return insights;

  const cashRow = assetRow(assets, "\u8d27\u5e01\u8d44\u91d1");
  const debtRow = assetRow(assets, "\u77ed\u671f\u501f\u6b3e");
  const ltiRow = assetRow(assets, "\u957f\u671f\u80a1\u6743\u6295\u8d44");

  if (cashRow && debtRow) {
    const gaps = companyColsForSnapshot(snapshot).map((col) => {
      const cash = cellNum(cashRow, col) ?? 0;
      const debt = cellNum(debtRow, col) ?? 0;
      if (cash <= 0 && debt <= 0) return null;
      return { name: companyName(col), netWan: cash - debt, debtWan: debt, cashWan: cash };
    }).filter(Boolean) as Array<{ name: string; netWan: number; debtWan: number; cashWan: number }>;

    const levered = gaps.filter((g) => g.debtWan > 10000).sort((a, b) => b.debtWan - a.debtWan)[0];
    if (levered) {
      insights.push({
        label: "\u77ed\u671f\u501f\u6b3e",
        headline: `${levered.name} \u77ed\u501f ${(levered.debtWan / 10000).toFixed(1)} \u4ebf\uff0c\u51c0\u73b0\u91d1 ${(levered.netWan / 10000).toFixed(1)} \u4ebf`,
        detail: "\u671f\u672b\u79d1\u76ee\u53ef\u76f4\u63a5\u8ba1\u7b97\u8d27\u5e01\u8d44\u91d1\u2212\u77ed\u501f\uff0c\u662f\u8d22\u52a1\u5f39\u6027\u7684\u7b2c\u4e00\u5c42\u5ea6\u91cf",
        tone: levered.netWan < levered.debtWan * 0.1 ? "warning" : "neutral",
      });
    }
  }

  if (ltiRow) {
    const ltiHeavy = companyColsForSnapshot(snapshot).map((col) => ({
      name: companyName(col),
      wan: cellNum(ltiRow, col) ?? 0,
    }))
      .filter((x) => x.wan > 50000)
      .sort((a, b) => b.wan - a.wan)[0];
    if (ltiHeavy) {
      insights.push({
        label: "\u957f\u671f\u6295\u8d44",
        headline: `${ltiHeavy.name} \u957f\u671f\u80a1\u6743\u6295\u8d44 ${(ltiHeavy.wan / 10000).toFixed(1)} \u4ebf`,
        detail: "\u6295\u8d44\u6027\u8d44\u4ea7\u5360\u6bd4\u9ad8\u65f6\uff0c\u9700\u8054\u7cfb\u603b\u8d44\u4ea7\u5468\u8f6c\u7387\u5224\u65ad\u662f\u5426\u62d6\u7d2f ROE",
        tone: "neutral",
      });
    }
  }

  const prepayRow = assetRow(assets, "\u9884\u4ed8\u6b3e\u9879");
  if (prepayRow) {
    const prepayHeavy = companyColsForSnapshot(snapshot).map((col) => ({
      name: companyName(col),
      wan: cellNum(prepayRow, col) ?? 0,
    }))
      .filter((x) => x.wan > 50000)
      .sort((a, b) => b.wan - a.wan)[0];
    if (prepayHeavy) {
      insights.push({
        label: "\u9884\u4ed8\u5360\u7528",
        headline: `${prepayHeavy.name} \u9884\u4ed8\u6b3e\u9879 ${(prepayHeavy.wan / 10000).toFixed(1)} \u4ebf`,
        detail: "\u5927\u989d\u9884\u4ed8\u53ef\u80fd\u538b\u4f4e\u901f\u52a8\u6bd4\u7387\uff0c\u5f71\u54cd\u77ed\u671f\u507f\u503a\u89c6\u89d2\u4e0b\u7684\u771f\u5b9e\u53ef\u52a8\u7528\u8d44\u91d1",
        tone: "neutral",
      });
    }
  }

  return insights.slice(0, 3);
}

/** sec-06-2：科目 YoY 变动（FP&A） */
export function deriveChangeFpaInsights(snapshot: CompetitorReportSnapshot): AnalystInsight[] {
  const assets = getTable(snapshot, "sec-06-1");
  const changes = getTable(snapshot, "sec-06-2");
  const insights: AnalystInsight[] = [];

  const cashChgRow = changeRow(changes, "\u8d27\u5e01\u8d44\u91d1");
  const cashEndRow = assetRow(assets, "\u8d27\u5e01\u8d44\u91d1");
  if (cashChgRow && cashEndRow) {
    const runways = companyColsForSnapshot(snapshot).map((col) => {
      const cashWan = cellNum(cashEndRow, col);
      const chg = cellNum(cashChgRow, col);
      if (cashWan == null || chg == null || chg >= 0 || cashWan <= 0) return null;
      const monthlyBurn = Math.abs(chg) / 12;
      if (monthlyBurn <= 0) return null;
      return { name: companyName(col), months: cashWan / monthlyBurn, cashYi: cashWan / 10000, monthlyBurnWan: monthlyBurn };
    }).filter(Boolean) as Array<{ name: string; months: number; cashYi: number; monthlyBurnWan: number }>;

    const stressed = runways.filter((r) => r.months < 24).sort((a, b) => a.months - b.months)[0];
    if (stressed) {
      insights.push({
        label: CL.cashRunway,
        headline: `${stressed.name} 现金跑道约 ${Math.round(stressed.months)} 个月`,
        detail: `期末货币资金 ${stressed.cashYi.toFixed(2)} 亿，按 YoY 消耗推算月均约 ${Math.round(stressed.monthlyBurnWan)} 万`,
        tone: stressed.months < 18 ? "negative" : "warning",
      });
    }
  }

  const stLoanChgRow = changeRow(changes, "\u77ed\u671f\u501f\u6b3e");
  if (stLoanChgRow) {
    const spike = companyColsForSnapshot(snapshot).map((col) => ({
      name: companyName(col),
      delta: cellNum(stLoanChgRow, col),
    }))
      .filter((x) => x.delta != null && x.delta > 50000)
      .sort((a, b) => b!.delta! - a!.delta!)[0];
    if (spike) {
      insights.push({
        label: "\u77ed\u501f\u53d8\u52a8",
        headline: `${spike.name} 短期借款 YoY +${Math.round(spike.delta! / 10000)} 亿`,
        detail: "\u8d44\u91d1\u7f3a\u53e3\u901a\u8fc7\u4fe1\u8d37\u8865\u8db3\u65f6\uff0c\u5e94\u8054\u7cfb\u6295\u8d44 CF \u4e0e\u51c0\u73b0\u91d1\u6536\u7a84\u5e45\u5ea6",
        tone: "warning",
      });
    }
  }

  const arChgRow = changeRow(changes, "\u5e94\u6536\u8d26\u6b3e");
  if (arChgRow) {
    const arDrop = companyColsForSnapshot(snapshot).map((col) => ({
      name: companyName(col),
      delta: cellNum(arChgRow, col),
    }))
      .filter((x) => x.delta != null && x.delta < -2000)
      .sort((a, b) => a!.delta! - b!.delta!)[0];
    if (arDrop) {
      insights.push({
        label: "\u5e94\u6536\u53d8\u52a8",
        headline: `${arDrop.name} 应收账款 YoY ${Math.round(arDrop.delta! / 100) / 100} 亿`,
        detail: "\u5927\u5e45\u4e0b\u964d\u53ef\u80fd\u6765\u81ea\u56de\u6b3e\u6539\u5584\u6216\u51c6\u5907\u8ba1\u63d0\uff0c\u9700\u8054\u7cfb\u8d26\u9f84\u5224\u65ad\u5229\u6da6\u8d28\u91cf",
        tone: "warning",
      });
    }
  }

  return insights.slice(0, 3);
}

/** sec-06-3：偿债与营运指标（FP&A） */
export function deriveLiquidityFpaInsights(snapshot: CompetitorReportSnapshot): AnalystInsight[] {
  const solvency = getTable(snapshot, "sec-06-3");
  const insights: AnalystInsight[] = [];

  const ratios = companyColsForSnapshot(snapshot).map((col) => ({
    name: companyName(col),
    v: tableMetric(solvency, FK_METRIC.currentRatio, col),
  })).filter((x) => x.v != null) as Array<{ name: string; v: number }>;

  if (ratios.length) {
    const tight = ratios.filter((r) => r.v < 1.2).sort((a, b) => a.v - b.v)[0];
    if (tight) {
      insights.push({
        label: "\u77ed\u671f\u507f\u503a",
        headline: `${tight.name} 流动比率 ${tight.v.toFixed(2)}，接近红线`,
        detail: "建议联系经营 CF 与短借覆盖能力一同判读（高杠杆+高 OCF 可对冲）",
        tone: tight.v < 1.16 ? "warning" : "neutral",
      });
    }
  }

  const netCashRows = companyColsForSnapshot(snapshot).map((col) => ({
    name: companyName(col),
    v: tableMetric(solvency, FK_METRIC.netCash, col),
  })).filter((x) => x.v != null) as Array<{ name: string; v: number }>;
  if (netCashRows.length >= 2) {
    const sorted = [...netCashRows].sort((a, b) => a.v - b.v);
    const tight = sorted[0]!;
    const leader = sorted[sorted.length - 1]!;
    if (leader.v > tight.v * 5) {
      insights.push({
        label: "\u51c0\u73b0\u91d1\u5206\u5c42",
        headline: `${leader.name} 净现金 ${leader.v.toFixed(1)} 亿 vs ${tight.name} ${tight.v.toFixed(1)} 亿`,
        detail: tight.v < 2 ? "短借补位或理财占用可能导致弹性收窄" : "净现金层次分化显著",
        tone: tight.v < 2 ? "warning" : "neutral",
      });
    }
  }

  const arStress = companyColsForSnapshot(snapshot).map((col) => {
    const raw = tableMetric(solvency, FK_METRIC.arToCurrent, col);
    if (raw == null) return null;
    return { name: companyName(col), pct: toPercentPoints(raw) };
  })
    .filter(Boolean)
    .sort((a, b) => b!.pct - a!.pct)[0];
  if (arStress && arStress.pct >= 12) {
    insights.push({
      label: "\u5e94\u6536\u8d28\u91cf",
      headline: `${arStress.name} 应收/流动资产 ${arStress.pct.toFixed(1)}% 为八家偏高`,
      detail: "需联系账龄与减值转回判断利润含金量",
      tone: "warning",
    });
  }

  const turnLeader = companyColsForSnapshot(snapshot).map((col) => {
    const t = tableMetric(solvency, FK_METRIC.assetTurnover, col);
    if (t == null) return null;
    return { name: companyName(col), t };
  })
    .filter(Boolean)
    .sort((a, b) => b!.t - a!.t)[0];
  if (turnLeader && turnLeader.t >= 1) {
    insights.push({
      label: "\u8d44\u4ea7\u6548\u7387",
      headline: `${turnLeader.name} 总资产周转 ${turnLeader.t.toFixed(2)}x 领先`,
      detail: "高周转是杜邦 ROE 的核心支撑因素之一",
      tone: "positive",
    });
  }

  return insights.slice(0, 3);
}

export function deriveProfitInsights(snapshot: CompetitorReportSnapshot): AnalystInsight[] {
  const fees = getTable(snapshot, "sec-07-3");
  const changes = getTable(snapshot, "sec-07-4");
  const insights: AnalystInsight[] = [];

  const grossRows = companyColsForSnapshot(snapshot).map((col) => {
    const g = tableMetric(fees, FK.grossMarginRate, col);
    const s = tableMetric(fees, FK.salesFeeRate, col);
    const a = tableMetric(fees, FK.adminFeeRate, col);
    const r = tableMetric(fees, FK.rndFeeRate, col);
    if (g == null) return null;
    const gross = toPercentPoints(g);
    const sales = s != null ? toPercentPoints(s) : 0;
    const admin = a != null ? toPercentPoints(a) : 0;
    const rnd = r != null ? toPercentPoints(r) : 0;
    const opMargin = gross - sales - admin - rnd;
    return { name: companyName(col), gross, sales, opMargin, totalFee: sales + admin + rnd };
  }).filter(Boolean) as Array<{ name: string; gross: number; sales: number; opMargin: number; totalFee: number }>;

  if (grossRows.length) {
    const buyModel = grossRows.filter((r) => r.sales >= 40).sort((a, b) => b.sales - a.sales)[0];
    if (buyModel) {
      insights.push({
        label: "\u5546\u4e1a\u6a21\u5f0f",
        headline: `${buyModel.name} \u9500\u552e\u8d39\u7528\u7387 ${buyModel.sales.toFixed(1)}%\uff0c\u5178\u578b\u4e70\u91cf\u9a71\u52a8`,
        detail: "\u9500\u552e\u8d39\u7528\u7387\u662f\u6838\u5fc3\u6210\u672c\u9879\uff0c\u9700\u8054\u7cfb LTV \u4e0e\u6536\u5165\u89c4\u6a21\u5224\u65ad\u662f\u5426\u5065\u5eb7",
        tone: "neutral",
      });
    }
    const inverted = grossRows.filter((r) => r.opMargin < 0).sort((a, b) => a.opMargin - b.opMargin)[0];
    if (inverted) {
      insights.push({
        label: "\u6210\u672c\u5012\u6302",
        headline: `${inverted.name} \u9690\u542b\u8425\u4e1a\u5229\u6da6\u7387 ${inverted.opMargin.toFixed(1)}%`,
        detail: `\u6bdb\u5229\u7387 ${inverted.gross.toFixed(1)}% \u96be\u4ee5\u8986\u76d6\u4e09\u9879\u8d39\u7528\u7387 ${inverted.totalFee.toFixed(1)}%`,
        tone: "negative",
      });
    }
  }

  if (changes?.rows.length) {
    const gmRow = changes.rows.find((r) => String(r[FK.changePct] ?? "") === FK.grossMarginRate);
    if (gmRow) {
      let best: { name: string; d: number } | null = null;
      for (const col of companyColsForSnapshot(snapshot)) {
        const raw = cellNum(gmRow, col);
        if (raw == null) continue;
        const d = raw;
        if (!best || d > best.d) best = { name: companyName(col), d };
      }
      if (best && best.d > 0) {
        insights.push({
          label: "\u6bdb\u5229\u6539\u5584",
          headline: `${best.name} \u6bdb\u5229\u7387\u540c\u6bd4 +${best.d.toFixed(1)} pct \u9886\u5148`,
          detail: "\u6210\u672c\u7aef\u6216\u4ea7\u54c1\u7ed3\u6784\u6539\u5584\u7684\u91cf\u5316\u4fe1\u53f7",
          tone: "positive",
        });
      }
    }
  }

  return insights.slice(0, 3);
}

/** sec-07-1：核心科目（FP&A） */
export function deriveProfitCoreInsights(snapshot: CompetitorReportSnapshot): AnalystInsight[] {
  const core = getTable(snapshot, "sec-07-1");
  const insights: AnalystInsight[] = [];
  const revRow = core?.rows.find((r) => String(r[FK.subject] ?? "").startsWith("\u8425\u4e1a\u6536\u5165"));
  const salesRow = core?.rows.find((r) => String(r[FK.subject] ?? "").startsWith("\u9500\u552e\u8d39\u7528"));
  const costRow = core?.rows.find((r) => String(r[FK.subject] ?? "").startsWith("\u8425\u4e1a\u6210\u672c"));
  const profitRow = core?.rows.find((r) => String(r[FK.subject] ?? "").startsWith("\u51c0\u5229\u6da6"));

  if (salesRow && costRow) {
    for (const col of companyColsForSnapshot(snapshot)) {
      const sales = cellNum(salesRow, col) ?? 0;
      const cost = cellNum(costRow, col) ?? 0;
      if (sales > cost && sales > 500000) {
        insights.push({
          label: "\u4e70\u91cf\u6210\u672c\u7ed3\u6784",
          headline: `${companyName(col)} \u9500\u552e\u8d39 ${(sales / 10000).toFixed(1)} \u4ebf > \u8425\u4e1a\u6210\u672c ${(cost / 10000).toFixed(1)} \u4ebf`,
          detail: "\u84dd\u672c\uff1a\u6d41\u91cf\u91c7\u4e70\u662f\u6700\u5927\u7684\u201c\u751f\u4ea7\u6210\u672c\u201d\uff0c\u9700\u8054\u7cfb LTV \u5224\u65ad\u4e70\u91cf\u6a21\u5f0f\u5065\u5eb7\u5ea6",
          tone: "neutral",
        });
        break;
      }
    }
  }

  if (profitRow) {
    const losses = companyColsForSnapshot(snapshot).map((col) => ({
      name: companyName(col),
      p: cellNum(profitRow, col),
    })).filter((x) => x.p != null && x.p < 0) as Array<{ name: string; p: number }>;
    if (losses.length) {
      const worst = losses.sort((a, b) => a.p - b.p)[0]!;
      insights.push({
        label: "\u4e8f\u635f\u89c4\u6a21",
        headline: `${worst.name} \u51c0\u5229\u6da6 ${(worst.p / 10000).toFixed(2)} \u4ebf`,
        detail: "\u9700\u533a\u5206\u4e00\u6b21\u6027\u51cf\u503c\u4e0e\u4e3b\u8425\u8425\u4e1a\u5229\u6da6\uff08\u89c1\u76c8\u4e8f\u9a71\u52a8\u8868\uff09",
        tone: "negative",
      });
    }
  }

  if (revRow && profitRow) {
    const yycqRev = parseNum(rowValueForCompany(revRow, SUBJECT_COL));
    const top = companyColsForSnapshot(snapshot).map((col) => ({
      name: companyName(col),
      rev: revRow ? cellNum(revRow, col) : null,
    }))
      .filter((x) => x.rev != null && x.rev > 0)
      .sort((a, b) => b!.rev! - a!.rev!)[0];
    if (top && yycqRev) {
      insights.push({
        label: "\u6536\u5165\u89c4\u6a21",
        headline: `${top.name} \u8425\u6536 ${(top.rev! / 10000).toFixed(0)} \u4ebf\u9886\u5148`,
        detail: `\u672c\u516c\u53f8 ${(yycqRev / 10000).toFixed(1)} \u4ebf\uff0c\u89c4\u6a21\u5dee\u5f02\u51b3\u5b9a\u8d39\u7528\u7387\u53ef\u627f\u53d7\u533a\u95f4`,
        tone: "neutral",
      });
    }
  }

  return insights.slice(0, 3);
}

/** sec-07-2：盈利驱动摘要（FP&A） */
export function deriveProfitDriverInsights(snapshot: CompetitorReportSnapshot): AnalystInsight[] {
  const drivers = getTable(snapshot, "sec-07-2");
  if (!drivers?.rows.length) return [];

  return drivers.rows.slice(0, 3).map((row) => {
    const name = String(row[FK.company] ?? "");
    const conclusion = String(row["\u7ed3\u8bba"] ?? "");
    const tone: InsightTone = conclusion.includes("\u4e8f\u635f") ? "negative" : conclusion.includes("\u589e\u66b4") || conclusion.includes("V\u578b") ? "positive" : "neutral";
    return {
      label: "\u76c8\u4e8f\u9a71\u52a8",
      headline: `${name} \u00b7 ${conclusion}`,
      detail: String(row["\u5173\u952e\u9a71\u52a8"] ?? "").slice(0, 120),
      tone,
    };
  });
}

/** sec-07-3：费用率（FP&A）— 沿用 deriveProfitInsights 逻辑 */
export function deriveFeeRateInsights(snapshot: CompetitorReportSnapshot): AnalystInsight[] {
  return deriveProfitInsights(snapshot);
}

/** sec-07-4：费用率 YoY（FP&A） */
export function deriveFeeRateChangeInsights(snapshot: CompetitorReportSnapshot): AnalystInsight[] {
  const changes = getTable(snapshot, "sec-07-4");
  const insights: AnalystInsight[] = [];

  const rndRow = changes?.rows.find((r) => String(r[FK.changePct] ?? "") === FK.rndFeeRate);
  if (rndRow) {
    let maxUp: { name: string; d: number } | null = null;
    for (const col of companyColsForSnapshot(snapshot)) {
      const raw = cellNum(rndRow, col);
      if (raw == null) continue;
      if (!maxUp || raw > maxUp.d) maxUp = { name: companyName(col), d: raw };
    }
    if (maxUp && maxUp.d > 3) {
      insights.push({
        label: "\u7814\u53d1\u6295\u5165",
        headline: `${maxUp.name} \u7814\u53d1\u8d39\u7528\u7387 +${maxUp.d.toFixed(1)} pct`,
        detail: "\u84dd\u672c\uff1aSLG \u65b0\u54c1\u7814\u53d1\u6295\u5165\u6301\u7eed\u589e\u52a0\uff0c\u9700\u8054\u7cfb\u7ba1\u7ebf\u4e0a\u7ebf\u8282\u594f",
        tone: "warning",
      });
    }
  }

  const salesRow = changes?.rows.find((r) => String(r[FK.changePct] ?? "") === FK.salesFeeRate);
  if (salesRow) {
    let bestCut: { name: string; d: number } | null = null;
    for (const col of companyColsForSnapshot(snapshot)) {
      const raw = cellNum(salesRow, col);
      if (raw == null || raw >= 0) continue;
      if (!bestCut || raw < bestCut.d) bestCut = { name: companyName(col), d: raw };
    }
    if (bestCut) {
      insights.push({
        label: "\u9500\u552e\u8d39\u7387\u6539\u5584",
        headline: `${bestCut.name} \u9500\u552e\u8d39\u7528\u7387 ${bestCut.d.toFixed(1)} pct`,
        detail: "V \u578b\u53cd\u8f6c\u5728\u8d39\u7528\u7aef\u7684\u91cf\u5316\u4fe1\u53f7\uff08\u5b8c\u7f8e\u4e16\u754c\u84dd\u672c\u53c2\u8003\uff09",
        tone: "positive",
      });
    }
  }

  const totalFeeDrop = changes?.rows.filter((r) => {
    const m = String(r[FK.changePct] ?? "");
    return m === FK.salesFeeRate || m === FK.adminFeeRate || m === FK.rndFeeRate;
  });
  if (totalFeeDrop?.length) {
    insights.push({
      label: "FP&A \u89c6\u89d2",
      headline: "\u8d39\u7528\u7387\u53d8\u52a8\u9700\u8054\u7cfb\u6536\u5165\u89c4\u6a21",
      detail: "\u51cf\u6536\u80cc\u666f\u4e0b\u8d39\u7528\u7387\u4e0b\u964d\u53ef\u80fd\u6765\u81ea\u6548\u7387\u6216\u8425\u6536\u640d\u5931\uff0c\u5206\u6bcd\u4e0e\u5206\u5b50\u540c\u6b65\u770b",
      tone: "neutral",
    });
  }

  return insights.slice(0, 3);
}

/** sec-07-5：费用额 YoY（FP&A） */
export function deriveFeeAmountInsights(snapshot: CompetitorReportSnapshot): AnalystInsight[] {
  const amounts = getTable(snapshot, "sec-07-5");
  const insights: AnalystInsight[] = [];

  const gmRow = amounts?.rows.find((r) => String(r[FK_AMOUNT_CHANGE] ?? "") === "\u6bdb\u5229");
  if (gmRow) {
    let best: { name: string; d: number } | null = null;
    for (const col of companyColsForSnapshot(snapshot)) {
      const raw = cellNum(gmRow, col);
      if (raw == null) continue;
      if (!best || raw > best.d) best = { name: companyName(col), d: raw };
    }
    if (best && best.d > 10000) {
      insights.push({
        label: "\u6bdb\u5229\u6539\u5584",
        headline: `${best.name} \u6bdb\u5229\u540c\u6bd4 +${(best.d / 10000).toFixed(1)} \u4ebf`,
        detail: "\u84dd\u672c\uff1a\u5b8c\u7f8e\u4e16\u754c V \u578b\u53cd\u8f6c\u6838\u5fc3\u9a9a\u5146\u4e4b\u4e00",
        tone: "positive",
      });
    }
  }

  const salesRow = amounts?.rows.find((r) => String(r[FK_AMOUNT_CHANGE] ?? "") === "\u9500\u552e\u8d39\u7528");
  if (salesRow) {
    let cut: { name: string; d: number } | null = null;
    for (const col of companyColsForSnapshot(snapshot)) {
      const raw = cellNum(salesRow, col);
      if (raw == null || raw >= 0) continue;
      if (!cut || raw < cut.d) cut = { name: companyName(col), d: raw };
    }
    if (cut && cut.d < -10000) {
      insights.push({
        label: "\u9500\u552e\u8d39\u8282\u7ea6",
        headline: `${cut.name} \u9500\u552e\u8d39\u7528\u8282\u7ea6 ${Math.abs(cut.d / 10000).toFixed(1)} \u4ebf`,
        detail: "\u7edd\u5bf9\u989d\u8282\u7ea6\u662f\u5229\u6da6\u4fee\u590d\u7684\u53ef\u89c6\u5316\u91cf\u5316",
        tone: "positive",
      });
    }
  }

  const rndRow = amounts?.rows.find((r) => String(r[FK_AMOUNT_CHANGE] ?? "") === "\u7814\u53d1\u8d39\u7528");
  if (rndRow) {
    let cut: { name: string; d: number } | null = null;
    for (const col of companyColsForSnapshot(snapshot)) {
      const raw = cellNum(rndRow, col);
      if (raw == null || raw >= 0) continue;
      if (!cut || raw < cut.d) cut = { name: companyName(col), d: raw };
    }
    if (cut && cut.d < -10000) {
      insights.push({
        label: "\u7814\u53d1\u8282\u7ea6",
        headline: `${cut.name} \u7814\u53d1\u8d39\u7528\u8282\u7ea6 ${Math.abs(cut.d / 10000).toFixed(1)} \u4ebf`,
        detail: "\u4e09\u91cd\u5171\u632f\u9a9a\u5146\uff1a\u9500\u552e/\u7814\u53d1\u8282\u7ea6 + \u51cf\u503c\u5305\u888b\u6d88\u5931",
        tone: "positive",
      });
    }
  }

  return insights.slice(0, 3);
}

function cfItemRow(table: TableBlock | undefined, labelPart: string) {
  return table?.rows.find((r) => String(r[FK_CF_ITEM] ?? "").replace(/\*\*/g, "").includes(labelPart));
}

/** sec-08-1：现金流量表科目（FP&A） */
export function deriveCfItemsInsights(snapshot: CompetitorReportSnapshot): AnalystInsight[] {
  const cf = getTable(snapshot, "sec-08-1");
  const insights: AnalystInsight[] = [];

  const ocfRow = cfItemRow(cf, "\u7ecf\u8425CF\u51c0\u989d");
  const icfRow = cfItemRow(cf, "\u6295\u8d44CF\u51c0\u989d");
  if (ocfRow) {
    const leader = companyColsForSnapshot(snapshot).map((col) => ({
      name: companyName(col),
      v: cellNum(ocfRow, col),
    }))
      .filter((x) => x.v != null && x.v > 0)
      .sort((a, b) => b!.v! - a!.v!)[0];
    if (leader) {
      insights.push({
        label: "\u7ecf\u8425 CF",
        headline: `${leader.name} \u7ecf\u8425 CF ${(leader.v! / 10000).toFixed(1)} \u4ebf\u9886\u5148`,
        detail: "\u73b0\u91d1\u9020\u8840\u80fd\u529b\u662f\u5224\u65ad\u771f\u6b63\u76c8\u5229\u7684\u7b2c\u4e00\u6b65",
        tone: "positive",
      });
    }
    const neg = companyColsForSnapshot(snapshot).map((col) => ({
      name: companyName(col),
      v: cellNum(ocfRow, col),
    })).filter((x) => x.v != null && x.v < 0);
    if (neg.length) {
      insights.push({
        label: "\u7ecf\u8425\u71c3\u70e7",
        headline: `${neg.map((n) => n.name).join("\u3001")} \u7ecf\u8425 CF \u4e3a\u8d1f`,
        detail: "\u84dd\u672c\uff1a\u534e\u6e05\u98de\u626c\u6301\u7eed\u201c\u70e7\u94b1\u201d\uff0c\u7eff\u5cb8\u9700\u8054\u7cfb\u5408\u540c\u8d1f\u503a",
        tone: "negative",
      });
    }
  }

  if (icfRow) {
    const outflow = companyColsForSnapshot(snapshot).map((col) => ({
      name: companyName(col),
      v: cellNum(icfRow, col),
    }))
      .filter((x) => x.v != null && x.v < -100000)
      .sort((a, b) => a!.v! - b!.v!)[0];
    if (outflow) {
      insights.push({
        label: "\u6295\u8d44 CF",
        headline: `${outflow.name} \u6295\u8d44\u6d41\u51fa ${Math.abs(outflow.v! / 10000).toFixed(1)} \u4ebf`,
        detail: "\u84dd\u672c\uff1a\u4e09\u4e03\u5927\u989d\u7406\u8d22\u6295\u8d44\u9a71\u52a8\uff0c\u975e\u7ecf\u8425\u4e8f\u635f\uff08\u8054\u7cfb sec-06 \u77ed\u501f\uff09",
        tone: "neutral",
      });
    }
  }

  return insights.slice(0, 3);
}

/** sec-08-2：沿用 deriveCashflowInsights */
export function deriveCfQualityInsights(snapshot: CompetitorReportSnapshot): AnalystInsight[] {
  return deriveCashflowInsights(snapshot);
}

/** sec-09-1：房租（FP&A） */
export function deriveRentInsights(snapshot: CompetitorReportSnapshot): AnalystInsight[] {
  const rent = getTable(snapshot, "sec-09-1");
  const insights: AnalystInsight[] = [];
  const perCapRow = rent?.rows.find((r) => String(r[FK.metric] ?? "") === FK_METRIC.rentPerCap);
  if (perCapRow) {
    const high = companyColsForSnapshot(snapshot).map((col) => ({
      name: companyName(col),
      v: cellNum(perCapRow, col),
    }))
      .filter((x) => x.v != null)
      .sort((a, b) => b!.v! - a!.v!)[0];
    const low = companyColsForSnapshot(snapshot).map((col) => ({
      name: companyName(col),
      v: cellNum(perCapRow, col),
    }))
      .filter((x) => x.v != null && x.v > 0)
      .sort((a, b) => a!.v! - b!.v!)[0];
    if (high && high.v! > 2500) {
      insights.push({
        label: "\u529e\u516c\u6210\u672c",
        headline: `${high.name} \u4eba\u5747\u6708\u623f\u79df ${Math.round(high.v!)} \u5143\u4e3a\u516b\u5bb6\u6700\u9ad8`,
        detail: "\u84dd\u672c\uff1a\u88c1\u5458\u540e\u9762\u79ef\u672a\u540c\u6b65\u7f29\u51cf\u53ef\u80fd\u626f\u5927\u4eba\u5747\u623f\u79df",
        tone: "warning",
      });
    }
    if (low && low.v! < 500) {
      insights.push({
        label: "\u529e\u516c\u7b56\u7565",
        headline: `${low.name} \u4eba\u5747\u6708\u623f\u79df\u4ec5 ${Math.round(low.v!)} \u5143`,
        detail: "\u84dd\u672c\uff1a\u6d77\u5916\u8fdc\u7a0b/\u81ea\u6709\u7269\u4e1a\u62c9\u4f4e\u4eba\u5747\u623f\u79df",
        tone: "neutral",
      });
    }
  }
  return insights.slice(0, 3);
}

/** sec-09-3：政府补助 */
export function deriveGovInsights(snapshot: CompetitorReportSnapshot): AnalystInsight[] {
  const gov = getTable(snapshot, "sec-09-3");
  const row2025 = gov?.rows.find((r) => String(r[FK.metric] ?? "").includes("2025"));
  if (!row2025) return [];
  const leader = companyColsForSnapshot(snapshot).map((col) => ({
    name: companyName(col),
    v: cellNum(row2025, col),
  }))
    .filter((x) => x.v != null)
    .sort((a, b) => b!.v! - a!.v!)[0];
  if (!leader) return [];
  return [
    {
      label: "\u653f\u7b56\u83b7\u53d6",
      headline: `${leader.name} 2025 \u653f\u5e9c\u8865\u52a9 ${(leader.v! / 10000).toFixed(2)} \u4ebf\u9886\u5148`,
      detail: "\u53cd\u6620 A \u80a1\u9f99\u5934\u653f\u7b56\u83b7\u53d6\u4e0e\u7a0e\u6536\u8fd4\u8fd8\u80fd\u529b",
      tone: "neutral",
    },
  ];
}

/** sec-09-4：在研项目 */
export function derivePipelineInsights(snapshot: CompetitorReportSnapshot): AnalystInsight[] {
  const projects = getTable(snapshot, "sec-09-4");
  if (!projects?.rows.length) return [];
  const byCompany = new Map<string, number>();
  for (const row of projects.rows) {
    const co = String(row[FK.company] ?? "");
    byCompany.set(co, (byCompany.get(co) ?? 0) + 1);
  }
  const richest = [...byCompany.entries()].sort((a, b) => b[1] - a[1])[0];
  const insights: AnalystInsight[] = [];
  if (richest) {
    insights.push({
      label: "\u7ba1\u7ebf\u5bbd\u5ea6",
      headline: `${richest[0]} \u5728\u7814\u9879\u76ee ${richest[1]} \u4e2a\u4e3a\u516b\u5bb6\u6700\u591a`,
      detail: "\u84dd\u672c\uff1a\u4e09\u4e03\u4e92\u5a31 11 \u9879\u5168\u90e8\u7814\u53d1\u4e2d\uff0c\u4ea7\u54c1\u50a8\u5907\u6700\u4e30\u5bcc",
      tone: "positive",
    });
  }
  const pixel = projects.rows.filter((r) => String(r[FK.company] ?? "").includes("\u50cf\u7d20"));
  if (pixel.length === 1) {
    insights.push({
      label: "\u96c6\u4e2d\u5ea6\u98ce\u9669",
      headline: "\u50cf\u7d20\u8f6f\u4ef6\u4ec5 1 \u4e2a\u5728\u7814\u9879\u76ee",
      detail: "\u84dd\u672c\uff1a\u661f\u9645\u7406\u60f3\u56fd\u7d2f\u8ba1\u6295\u5165 2.10 \u4ebf\u5360\u603b\u8d44\u4ea7 39%\uff0c\u6210\u8d25\u51b3\u5b9a\u5b58\u4ea1",
      tone: "warning",
    });
  }
  return insights.slice(0, 3);
}

/** sec-09-6：币种结构 */
export function deriveCurrencyInsights(snapshot: CompetitorReportSnapshot): AnalystInsight[] {
  const cur = getTable(snapshot, "sec-09-6");
  const fxRow = cur?.rows.find((r) => String(r[FK.metric] ?? "").includes("\u5916\u5e01\u5360\u6bd4"));
  if (!fxRow) return [];
  const high = companyColsForSnapshot(snapshot).map((col) => ({
    name: companyName(col),
    pct: rowValueForCompany(fxRow, col) != null ? toPercentPoints(cellNum(fxRow, col) ?? 0) : null,
  }))
    .filter((x) => x.pct != null)
    .sort((a, b) => b!.pct! - a!.pct!)[0];
  if (!high || high.pct! < 50) return [];
  return [
    {
      label: "\u6c47\u7387\u98ce\u9669",
      headline: `${high.name} \u5916\u5e01\u5360\u6bd4 ${high.pct!.toFixed(1)}%`,
      detail: "\u84dd\u672c\uff1a\u5883\u5916\u6536\u5165\u7559\u5b58\u6d77\u5916\u672a\u7ed3\u6c47\uff0c\u5168\u7403\u5316\u6df1\u5ea6\u6307\u6807",
      tone: "neutral",
    },
  ];
}

/** sec-09-7：投资理财 */
export function deriveInvestmentInsights(snapshot: CompetitorReportSnapshot): AnalystInsight[] {
  const inv = getTable(snapshot, "sec-09-7");
  const totalRow = inv?.rows.find((r) => String(r[FK.subject] ?? "").startsWith("\u5408\u8ba1"));
  if (!totalRow) return [];
  const leader = companyColsForSnapshot(snapshot).map((col) => ({
    name: companyName(col),
    v: cellNum(totalRow, col),
  }))
    .filter((x) => x.v != null && x.v > 0)
    .sort((a, b) => b!.v! - a!.v!)[0];
  if (!leader) return [];
  return [
    {
      label: "\u8d44\u91d1\u914d\u7f6e",
      headline: `${leader.name} \u7406\u8d22\u6295\u8d44 ${(leader.v! / 10000).toFixed(1)} \u4ebf`,
      detail: "\u84dd\u672c\uff1a\u4e09\u4e03 60 \u4ebf+\u7406\u8d22\u5c45\u9996\uff0c\u8054\u7cfb\u6295\u8d44 CF \u4e0e\u77ed\u501f",
      tone: "neutral",
    },
  ];
}

/** sec-09-8：应收账龄 */
export function deriveArAgingInsights(snapshot: CompetitorReportSnapshot): AnalystInsight[] {
  const ar = getTable(snapshot, "sec-09-8");
  if (!ar?.rows.length) return [];
  const insights: AnalystInsight[] = [];
  for (const row of ar.rows) {
    const co = String(row[FK.company] ?? "");
    const overPct = parseNum(row["1\u5e74\u4ee5\u4e0a\u5360\u6bd4"]);
    if (overPct != null && toPercentPoints(overPct) >= 40) {
      insights.push({
        label: "\u8d26\u9f84\u98ce\u9669",
        headline: `${co} 1 \u5e74\u4ee5\u4e0a\u5e94\u6536\u5360\u6bd4 ${toPercentPoints(overPct).toFixed(1)}%`,
        detail: "\u84dd\u672c\uff1a\u5854\u4eba\u7f51\u7edc\u5df2\u5927\u989d\u8ba1\u63d0\uff0c\u5229\u6da6\u589e\u957f\u9700\u201c\u6324\u6c34\u5206\u201d",
        tone: "warning",
      });
      break;
    }
  }
  return insights.slice(0, 3);
}

/** sec-09-9：运营产品 */
export function deriveProductsInsights(snapshot: CompetitorReportSnapshot): AnalystInsight[] {
  const products = getTable(snapshot, "sec-09-9");
  if (!products?.rows.length) return [];
  const byCo = new Map<string, number>();
  for (const row of products.rows) {
    const co = String(row[FK.company] ?? "");
    byCo.set(co, (byCo.get(co) ?? 0) + 1);
  }
  const yycq = byCo.get(SUBJECT_COL) ?? byCo.get("YYCQ") ?? 0;
  return [
    {
      label: "\u4ea7\u54c1\u77e9\u9635",
      headline: `\u672c\u516c\u53f8\u8fd0\u8425\u4ea7\u54c1 ${yycq > 0 ? "多 SKU" : "见表"}`,
      detail: "\u84dd\u672c\uff1a7 \u6b3e IP \u53cc\u7aef\u5747\u8861\uff0c\u4f46\u5728\u7814\u4ec5 1 \u9879\u2014\u7ba1\u7ebf\u5355\u8584",
      tone: yycq >= 5 ? "neutral" : "warning",
    },
  ];
}

export function deriveCashflowInsights(snapshot: CompetitorReportSnapshot): AnalystInsight[] {
  const points = parseCashQualityPoints(snapshot);
  const insights: AnalystInsight[] = [];

  const tierA = points.filter((p) => p.tier === "A");
  if (tierA.length) {
    const names = tierA.map((p) => p.name).join("\u3001");
    insights.push({
      label: "\u5229\u6da6\u542b\u91d1\u91cf",
      headline: `${names} \u7ecf\u8425 CF/\u51c0\u5229 \u2265 120%`,
      detail: "\u5229\u6da6\u6709\u73b0\u91d1\u652f\u6491\uff0c\u6392\u9664\u5927\u89c4\u6a21\u51cf\u503c\u540e\u8d28\u91cf\u53ef\u9760",
      tone: "positive",
    });
  }

  const hollow = points.filter((p) => p.tier === "D" && p.profit > 0);
  if (hollow.length) {
    const p = hollow[0]!;
    insights.push({
      label: "\u865a\u76c8\u9884\u8b66",
      headline: `${p.name} \u51c0\u5229\u6da6\u4e3a\u6b63\u4f46\u7ecf\u8425 CF \u4e3a\u8d1f`,
      detail: "\u5229\u6da6\u8868\u4e0e\u73b0\u91d1\u8868\u526a\u5200\u5dee\uff0c\u9700\u8054\u7cfb\u5408\u540c\u8d1f\u503a\u4e0e\u9884\u6536\u6b3e\u53d8\u5316",
      tone: "negative",
    });
  }

  const inflated = points.filter((p) => p.tier === "A" && p.ratioPct > 140);
  if (inflated.length) {
    const p = inflated.find((x) => x.name.includes("\u50cf\u7d20")) ?? inflated[0]!;
    insights.push({
      label: "\u4f1a\u8ba1\u89c6\u89d2",
      headline: `${p.name} CF/\u51c0\u5229 ${p.ratioPct.toFixed(0)}% \u504f\u9ad8\u9700\u6838\u5bf9`,
      detail: "\u7814\u53d1\u8d39\u7528\u5316\u5904\u7406\u53ef\u80fd\u628a\u73b0\u91d1\u652f\u51fa\u79fb\u51fa\u7ecf\u8425\u6d3b\u52a8\uff0c\u542b\u91d1\u91cf\u9700\u8c03\u6574\u540e\u518d\u8bfb",
      tone: "warning",
    });
  }

  return insights.slice(0, 3);
}

export function deriveRoiInsights(snapshot: CompetitorReportSnapshot): AnalystInsight[] {
  const roi = getTable(snapshot, "sec-09-2");
  const insights: AnalystInsight[] = [];

  const roiRow = roi?.rows.find((r) => String(r[FK.metric] ?? "") === FK_METRIC.compositeRoi);
  const adRow = roi?.rows.find((r) => String(r[FK.metric] ?? "") === FK_METRIC.adSalesRatio);

  if (roiRow && adRow) {
    const pairs = companyColsForSnapshot(snapshot).map((col) => {
      const r = cellNum(roiRow, col);
      const ad = cellNum(adRow, col);
      if (r == null || ad == null) return null;
      return { name: companyName(col), roi: r, adShare: toPercentPoints(ad) };
    }).filter(Boolean) as Array<{ name: string; roi: number; adShare: number }>;

    const buyLowRoi = pairs.filter((p) => p.adShare >= 85).sort((a, b) => a.roi - b.roi)[0];
    if (buyLowRoi) {
      insights.push({
        label: "ROI \u89e3\u8bfb",
        headline: `${buyLowRoi.name} \u7efc\u5408 ROI ${buyLowRoi.roi.toFixed(1)}x \u4f46\u5e7f\u544a\u5360\u6bd4 ${buyLowRoi.adShare.toFixed(0)}%`,
        detail: "\u4e70\u91cf\u578b\u516c\u53f8 ROI \u504f\u4f4e\u662f\u6a21\u5f0f\u7279\u5f81\uff0c\u5173\u952e\u5728 LTV \u662f\u5426\u8986\u76d6\u83b7\u5ba2\u6210\u672c",
        tone: "neutral",
      });
    }
    const organic = pairs.filter((p) => p.adShare < 30).sort((a, b) => b.roi - a.roi)[0];
    if (organic) {
      insights.push({
        label: "\u83b7\u5ba2\u7ed3\u6784",
        headline: `${organic.name} ROI ${organic.roi.toFixed(1)}x \u4f46\u5e7f\u544a\u4ec5\u5360\u9500\u552e\u8d39 ${organic.adShare.toFixed(0)}%`,
        detail: "\u9ad8 ROI \u53cd\u6620\u4f4e\u63a8\u5e7f\u9700\u6c42\uff0c\u4e0d\u7b49\u4e8e\u589e\u957f\u6f5c\u529b\u5f3a\uff08\u8001\u7528\u6237/\u6e20\u9053\u9a71\u52a8\uff09",
        tone: "warning",
      });
    }
  }

  return insights.slice(0, 3);
}

export function acquisitionModel(adSharePct: number): { model: AcquisitionModel; label: string } {
  if (adSharePct >= 75) return { model: "buy", label: "\u4e70\u91cf\u578b" };
  if (adSharePct >= 45) return { model: "brand", label: "\u54c1\u724c+\u6e20\u9053" };
  if (adSharePct >= 20) return { model: "channel", label: "\u6e20\u9053\u4f9d\u6258" };
  return { model: "organic", label: "\u81ea\u7136\u6d41\u91cf" };
}

export function computeOperatingMargins(snapshot: CompetitorReportSnapshot) {
  const fees = getTable(snapshot, "sec-07-3");
  return companyColsForSnapshot(snapshot).map((col) => {
    const g = tableMetric(fees, FK.grossMarginRate, col);
    const s = tableMetric(fees, FK.salesFeeRate, col);
    const a = tableMetric(fees, FK.adminFeeRate, col);
    const r = tableMetric(fees, FK.rndFeeRate, col);
    if (g == null) return null;
    const gross = toPercentPoints(g);
    const sales = s != null ? toPercentPoints(s) : 0;
    const admin = a != null ? toPercentPoints(a) : 0;
    const rnd = r != null ? toPercentPoints(r) : 0;
    return {
      colKey: col,
      name: companyName(col),
      gross,
      sales,
      opMargin: round2(gross - sales - admin - rnd),
    };
  }).filter(Boolean) as Array<{ colKey: string; name: string; gross: number; sales: number; opMargin: number }>;
}
