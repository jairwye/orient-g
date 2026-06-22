import {
  colKeyForDisplayLabel,
  colToLabel,
  COMPANY_COLS,
  getCompanyContext,
  isSubjectCol,
  labelToCol,
  subjectUiLabel,
} from "./companies";
import type { CompetitorReportSnapshot } from "./types";
import type { AnalystInsight, InsightTone } from "./finance_analysis";
import { formatNarrative, type FormatNarrativeOptions, type NarrativePart } from "./narrative_format";

export type SubjectBullet = {
  text: string;
  tone?: InsightTone;
  tag?: string;
};

export type SubjectAnalysisGroup = {
  company: string;
  colKey: string;
  bullets: SubjectBullet[];
};

type LabelCtx = {
  labelsByLength: string[];
  labelOrder: string[];
  colKeyForLabel: (label: string) => string;
  formatOpts: FormatNarrativeOptions;
};

const FALLBACK_CTX: LabelCtx = (() => {
  const labels = COMPANY_COLS.map((c) => colToLabel(c));
  return {
    labelsByLength: [...labels].sort((a, b) => b.length - a.length),
    labelOrder: labels,
    colKeyForLabel: (l) => labelToCol(l),
    formatOpts: {},
  };
})();

function labelCtxFor(snapshot?: CompetitorReportSnapshot): LabelCtx {
  if (!snapshot?.companies?.length) return FALLBACK_CTX;
  const ctx = getCompanyContext(snapshot);
  const fromSnap = snapshot.companies.flatMap((c) => [c.label, c.short].filter(Boolean) as string[]);
  const labelOrder = [...new Set([...ctx.labels, ...fromSnap])];
  const labelsByLength = [...labelOrder].sort((a, b) => b.length - a.length);
  return {
    labelsByLength,
    labelOrder,
    colKeyForLabel: (l) => colKeyForDisplayLabel(l, snapshot),
    formatOpts: { snapshot },
  };
}

/** 句首公司名（含「XX的」「XX（」） */
function detectCompanyPrefix(text: string, ctx: LabelCtx): string | null {
  const t = text.trim();
  for (const label of ctx.labelsByLength) {
    if (t.startsWith(label)) return label;
    if (t.startsWith(`${label}的`)) return label;
    if (t.startsWith(`${label}（`) || t.startsWith(`${label}(`)) return label;
  }
  return null;
}

/** 文中出现的公司名（按首次出现排序、去重） */
function findCompaniesInText(text: string, ctx: LabelCtx): string[] {
  type Hit = { label: string; index: number };
  const hits: Hit[] = [];
  for (const label of ctx.labelsByLength) {
    let start = 0;
    while (start < text.length) {
      const idx = text.indexOf(label, start);
      if (idx === -1) break;
      const overlaps = hits.some((h) => idx >= h.index && idx < h.index + h.label.length);
      if (!overlaps) hits.push({ label, index: idx });
      start = idx + label.length;
    }
  }
  hits.sort((a, b) => a.index - b.index);
  const seen = new Set<string>();
  const ordered: string[] = [];
  for (const h of hits) {
    if (!seen.has(h.label)) {
      seen.add(h.label);
      ordered.push(h.label);
    }
  }
  return ordered;
}

/** 从标题（含「净现金——可比公司C…」）提取主体 */
export function detectCompanyInTitle(title: string, snapshot?: CompetitorReportSnapshot): string | null {
  const ctx = labelCtxFor(snapshot);
  const prefix = detectCompanyPrefix(title, ctx);
  if (prefix) return prefix;
  const afterDash = title.match(/[—–-]+([^—–-]+)/);
  if (afterDash) {
    const co = detectCompanyPrefix(afterDash[1], ctx) ?? findCompaniesInText(afterDash[1], ctx)[0];
    if (co) return co;
  }
  const mentioned = findCompaniesInText(title, ctx);
  if (mentioned.length === 1) return mentioned[0];
  if (mentioned.length > 1) return mentioned[0];
  return null;
}

/** 推断段落/洞察的主归属公司 */
function findPrimaryCompany(text: string, ctx: LabelCtx): string | null {
  const prefix = detectCompanyPrefix(text, ctx);
  if (prefix) return prefix;
  const mentioned = findCompaniesInText(text, ctx);
  if (mentioned.length === 1) return mentioned[0];
  if (mentioned.length > 1) {
    const first = mentioned[0]!;
    const idx = text.indexOf(first);
    if (idx <= 8) return first;
  }
  return null;
}

function stripCompanyLead(text: string, company: string): string {
  let body = text.trim();
  if (body.startsWith(company)) {
    body = body.slice(company.length).replace(/^[，,：:\s的]+/, "").trim();
  }
  return body || text.trim();
}

function normalizeBulletKey(text: string): string {
  return text.replace(/\s+/g, "").replace(/[，,。；;：:！!？?、]/g, "").toLowerCase();
}

/** 叙事与 FP&A 洞察合并后去重 */
export function dedupeSubjectBullets(bullets: SubjectBullet[]): SubjectBullet[] {
  const kept: SubjectBullet[] = [];
  const keys: string[] = [];

  for (const bullet of bullets) {
    const key = normalizeBulletKey(bullet.text);
    if (!key) continue;

    let dup = false;
    for (const existing of keys) {
      if (existing === key || existing.includes(key) || key.includes(existing)) {
        dup = true;
        break;
      }
    }
    if (dup) continue;

    keys.push(key);
    kept.push(bullet);
  }

  return kept;
}

function ensureBucket(buckets: Map<string, SubjectBullet[]>, company: string): SubjectBullet[] {
  if (!buckets.has(company)) buckets.set(company, []);
  return buckets.get(company)!;
}

function pushBullet(
  buckets: Map<string, SubjectBullet[]>,
  company: string,
  bullet: SubjectBullet,
): string {
  ensureBucket(buckets, company).push(bullet);
  return company;
}

function isGenericAnalysisLead(text: string, ctx: LabelCtx): boolean {
  if (findCompaniesInText(text, ctx).length) return false;
  const t = text.trim();
  if (t.length <= 28 && /反映|分化|说明|速览|关注线/.test(t)) return true;
  return false;
}

function ingestParagraph(
  buckets: Map<string, SubjectBullet[]>,
  text: string,
  activeCompany: string | null,
  ctx: LabelCtx,
): string | null {
  const trimmed = text.trim();
  if (!trimmed || isGenericAnalysisLead(trimmed, ctx)) return activeCompany;

  const explicit = findPrimaryCompany(trimmed, ctx);
  const company = explicit ?? activeCompany;
  if (!company) {
    return null;
  }

  const body = explicit ? stripCompanyLead(trimmed, explicit) : trimmed;
  pushBullet(buckets, company, { text: body });
  return company;
}

function ingestPart(
  buckets: Map<string, SubjectBullet[]>,
  part: NarrativePart,
  activeCompany: string | null,
  ctx: LabelCtx,
): string | null {
  if (part.kind === "company") {
    const text = part.text.trim();
    if (text) pushBullet(buckets, part.company, { text });
    return part.company;
  }

  if (part.kind === "paragraph") {
    return ingestParagraph(buckets, part.text, activeCompany, ctx);
  }

  if (part.kind === "list") {
    let cur = activeCompany;
    for (const item of part.items) {
      cur = ingestParagraph(buckets, item, cur, ctx);
    }
    return cur;
  }

  if (part.kind === "section") {
    const titleCo = detectCompanyInTitle(part.title, ctx.formatOpts.snapshot);
    let cur = titleCo ?? activeCompany;

    if (part.title.trim() && titleCo) {
      const titleText = part.title.replace(/^[^：:——\-—]+[：:——\-—]\s*/, "").trim() || part.title.trim();
      pushBullet(buckets, titleCo, { text: titleText });
      cur = titleCo;
    } else if (part.title.trim() && !part.body?.trim()) {
      cur = ingestParagraph(buckets, part.title, cur, ctx) ?? cur;
    }

    if (part.body?.trim()) {
      for (const sub of formatNarrative(part.body, {
        splitCompanies: true,
        stripAnalysisPrefix: true,
        ...ctx.formatOpts,
      })) {
        cur = ingestPart(buckets, sub, cur, ctx);
      }
    }
    return cur;
  }

  return activeCompany;
}

function insightToBullet(ins: AnalystInsight, company: string): SubjectBullet {
  let text = ins.headline;
  if (text.startsWith(company)) {
    text = text.slice(company.length).replace(/^[，,：:\s·]+/, "").trim();
  }
  if (ins.detail) {
    text = text ? `${text}。${ins.detail}` : ins.detail;
  }
  return { text: text || ins.headline, tone: ins.tone, tag: ins.label };
}

/** 将叙事 + FP&A 洞察按公司主体合并为分组列表 */
export function buildSubjectAnalysisGroups(
  markdown: string,
  insights: AnalystInsight[],
  snapshot?: CompetitorReportSnapshot,
): SubjectAnalysisGroup[] {
  const ctx = labelCtxFor(snapshot);
  const buckets = new Map<string, SubjectBullet[]>();

  let activeCompany: string | null = null;
  for (const part of formatNarrative(markdown, {
    splitCompanies: true,
    stripAnalysisPrefix: true,
    ...ctx.formatOpts,
  })) {
    activeCompany = ingestPart(buckets, part, activeCompany, ctx);
  }

  for (const ins of insights) {
    const co =
      findPrimaryCompany(ins.headline, ctx) ??
      (ins.detail ? findPrimaryCompany(ins.detail, ctx) : null) ??
      findPrimaryCompany(`${ins.headline} ${ins.detail ?? ""}`, ctx);
    if (co) {
      pushBullet(buckets, co, insightToBullet(ins, co));
    }
  }

  return ctx.labelOrder
    .filter((co) => (buckets.get(co)?.length ?? 0) > 0)
    .map((co) => ({
      company: isSubjectCol(co) ? subjectUiLabel(snapshot) : co,
      colKey: ctx.colKeyForLabel(co),
      bullets: buckets.get(co)!,
    }));
}
