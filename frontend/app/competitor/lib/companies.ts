/** 竞品财报 MD 表头中的公司列名（与 snapshot 一致） */
export const COMPANY_COLS = [
  "YYCQ",
  "三七互娱",
  "完美世界",
  "掌趣科技",
  "塔人网络",
  "华清飞扬",
  "像素软件",
  "绿岸网络",
] as const;

export function colToLabel(col: string): string {
  return col === "YYCQ" ? "游艺春秋" : col;
}

export function labelToCol(label: string): string {
  if (label === "游艺春秋" || label === "YYCQ") return "YYCQ";
  return label;
}
