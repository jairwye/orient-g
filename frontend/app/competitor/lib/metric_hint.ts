/** 从 KPI 值文案提取括号内公司名，用于「N家（公司…）」类指标 */
export function extractCompaniesHint(raw: string | number | null | undefined): string | undefined {
  if (raw == null) return undefined;
  const text = String(raw).trim();
  const paren = text.match(/[（(]([^）)]+)[）)]/);
  if (!paren?.[1]) return undefined;
  return paren[1]
    .split(/[/／、,，]/)
    .map((s) => s.trim())
    .filter(Boolean)
    .join(" · ");
}

export function isGrowthCompanyMetric(label: string): boolean {
  return label.includes("正增长") && (label.includes("营收") || label.includes("净利"));
}
