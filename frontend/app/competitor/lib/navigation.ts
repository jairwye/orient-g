/** 九屏主导航 + 每屏细分 snap 锚点（与 ProgressScale 一致）；蓝本止于 sec-09 */
export type NavSub = { id: string; title: string };
export type NavSection = { id: string; title: string; subs: NavSub[] };

export type ScaleEntry = {
  snapId: string;
  /** hover 图例完整文案 */
  fullLabel: string;
  kind: "main" | "sub";
};

export const NAV_SECTIONS: NavSection[] = [
  {
    id: "sec-01",
    title: "行业总览",
    subs: [
      { id: "sec-01-a", title: "行业格局" },
      { id: "sec-01-b", title: "KPI与商业模式" },
    ],
  },
  {
    id: "sec-02",
    title: "综合排名",
    subs: [{ id: "sec-02-a", title: "评分与雷达" }],
  },
  {
    id: "sec-03",
    title: "经营成果",
    subs: [{ id: "sec-03-a", title: "指标与结论" }],
  },
  {
    id: "sec-04",
    title: "人员与人效",
    subs: [{ id: "sec-04-a", title: "人员全景" }],
  },
  {
    id: "sec-05",
    title: "收入成本",
    subs: [
      { id: "sec-05-a", title: "产品收入" },
      { id: "sec-05-b", title: "经营地区" },
    ],
  },
  {
    id: "sec-06",
    title: "资产负债",
    subs: [
      { id: "sec-06-a", title: "关键科目与变动" },
      { id: "sec-06-b", title: "偿债与杜邦" },
    ],
  },
  {
    id: "sec-07",
    title: "利润费用",
    subs: [
      { id: "sec-07-a", title: "盈利解读" },
      { id: "sec-07-c", title: "费用分析" },
    ],
  },
  {
    id: "sec-08",
    title: "现金流量",
    subs: [{ id: "sec-08-a", title: "现金流分析" }],
  },
  {
    id: "sec-09",
    title: "细节补充",
    subs: [
      { id: "sec-09-a", title: "房租" },
      { id: "sec-09-b", title: "广告ROI" },
      { id: "sec-09-c", title: "政府补助" },
      { id: "sec-09-d", title: "在研项目" },
      { id: "sec-09-e", title: "股东分红" },
      { id: "sec-09-f", title: "币种结构" },
      { id: "sec-09-g", title: "投资理财" },
      { id: "sec-09-h", title: "应收账龄" },
      { id: "sec-09-i", title: "运营产品" },
      { id: "sec-09-j", title: "主要游戏情况" },
      { id: "sec-09-k", title: "游戏数据" },
      { id: "sec-09-l", title: "关联方交易" },
      { id: "sec-09-m", title: "重要客商" },
      { id: "sec-09-n", title: "合并范围变更" },
      { id: "sec-09-o", title: "关联方变更" },
    ],
  },
  {
    id: "sec-10",
    title: "详情链接",
    subs: [{ id: "sec-10-a", title: "纵向对比入口" }],
  },
];

export const ALL_SNAP_IDS = NAV_SECTIONS.flatMap((s) => s.subs.map((sub) => sub.id));

export function buildScaleEntries(): ScaleEntry[] {
  const entries: ScaleEntry[] = [];
  for (const section of NAV_SECTIONS) {
    section.subs.forEach((sub, idx) => {
      entries.push({
        snapId: sub.id,
        fullLabel: `${section.title} · ${sub.title}`,
        kind: idx === 0 ? "main" : "sub",
      });
    });
  }
  return entries;
}

export function sectionIdFromSnap(snapId: string): string {
  return snapId.replace(/-[a-z]$/, "");
}

export function sectionTitle(snapId: string): string {
  const secId = sectionIdFromSnap(snapId);
  return NAV_SECTIONS.find((s) => s.id === secId)?.title ?? "\u7ade\u54c1\u8d22\u62a5";
}

export function subTitleForSnap(snapId: string): string {
  const secId = sectionIdFromSnap(snapId);
  return NAV_SECTIONS.find((s) => s.id === secId)?.subs.find((sub) => sub.id === snapId)?.title ?? snapId;
}
