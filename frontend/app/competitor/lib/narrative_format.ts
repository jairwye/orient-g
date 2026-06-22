import { companyLabelsForSnapshot, getCompanyContext } from "./companies";
import type { CompetitorReportSnapshot } from "./types";

export type NarrativePart =
  | { kind: "section"; title: string; body?: string }
  | { kind: "company"; company: string; text: string }
  | { kind: "paragraph"; text: string }
  | { kind: "list"; items: string[] };

/** 段内 (1)(2)(3) 枚举 */
function splitInlineNumberedItems(text: string): NarrativePart[] | null {
  const parts = text
    .split(/(?=\(\d+\))/)
    .map((s) => s.trim())
    .filter(Boolean);
  if (parts.length >= 2 && parts.every((p) => /^\(\d+\)/.test(p))) {
    return [{ kind: "list", items: parts }];
  }
  return null;
}

export type FormatNarrativeOptions = {
  /** 默认 true；plain 叙事关闭按公司名拆卡片 */
  splitCompanies?: boolean;
  /** 隐藏「分析——」类小标题，正文按主体拆行 */
  stripAnalysisPrefix?: boolean;
  /** 传入 snapshot 时用真实公司名拆分叙事（非匿名「可比公司A」） */
  snapshot?: CompetitorReportSnapshot;
};

function narrativeLabels(opts: FormatNarrativeOptions): string[] {
  if (opts.snapshot?.companies?.length) {
    return [...getCompanyContext(opts.snapshot).labelOrder];
  }
  return companyLabelsForSnapshot();
}

function isAnalysisTitle(title: string): boolean {
  return /^分析/.test(title.trim());
}

/** 跨主体小结（按分号拆句、按「A和B」拆并列主体） */
function isSynthesisTitle(title: string): boolean {
  return /^(综合判断|小结|总结)/.test(title.trim());
}

function detectCompanyAtStart(text: string, labels: string[]): string | null {
  const t = text.trim();
  for (const label of labels) {
    if (t.startsWith(label)) return label;
  }
  return null;
}

function stripCompanyLeadText(text: string, company: string): string {
  let body = text.trim();
  if (body.startsWith(company)) {
    body = body.slice(company.length).replace(/^[，,：:\s]+/, "").trim();
  }
  return body || text.trim();
}

/** 综合判断等：按；拆句，再处理「A和B」并列 */
function splitSynthesisClauses(text: string, opts: FormatNarrativeOptions): NarrativePart[] {
  const labels = [...narrativeLabels(opts)].sort((a, b) => b.length - a.length);
  const clauses = text
    .split(/[；;]/)
    .map((s) => s.trim())
    .filter(Boolean);
  const parts: NarrativePart[] = [];

  for (const clause of clauses) {
    const andIdx = clause.indexOf("和");
    if (andIdx > -1) {
      const left = clause.slice(0, andIdx).trim();
      const right = clause.slice(andIdx + 1).trim();
      const coLeft = detectCompanyAtStart(left, labels);
      const coRight = detectCompanyAtStart(right, labels);
      if (coLeft && coRight && coLeft !== coRight) {
        const leftBody = stripCompanyLeadText(left, coLeft);
        const rightBody = stripCompanyLeadText(right, coRight);
        const sharedTail = rightBody.replace(/^[-+]?[\d.,%]+/, "").trim();
        parts.push({
          kind: "company",
          company: coLeft,
          text: sharedTail ? `${leftBody}${sharedTail}` : leftBody,
        });
        parts.push({ kind: "company", company: coRight, text: rightBody });
        continue;
      }
    }

    const co = detectCompanyAtStart(clause, labels);
    if (co) {
      parts.push({ kind: "company", company: co, text: stripCompanyLeadText(clause, co) });
    } else {
      parts.push({ kind: "paragraph", text: clause });
    }
  }

  return parts.length ? parts : [{ kind: "paragraph", text: text.trim() }];
}

function shouldEmitSectionTitle(title: string, stripAnalysisPrefix: boolean): boolean {
  if (!title.trim()) return false;
  if (stripAnalysisPrefix && isAnalysisTitle(title)) return false;
  return true;
}

function appendSectionBody(
  out: NarrativePart[],
  title: string,
  body: string,
  opts: FormatNarrativeOptions,
) {
  const splitCompanies = opts.splitCompanies !== false;
  const stripAnalysisPrefix = opts.stripAnalysisPrefix === true;
  const numbered = splitInlineNumberedItems(body);
  if (numbered) {
    if (shouldEmitSectionTitle(title, stripAnalysisPrefix)) {
      out.push({ kind: "section", title });
    }
    out.push(...numbered);
    return;
  }
  if (isSynthesisTitle(title)) {
    out.push(...splitSynthesisClauses(body, opts));
    return;
  }
  if (!splitCompanies) {
    if (shouldEmitSectionTitle(title, stripAnalysisPrefix)) {
      out.push({ kind: "section", title, body });
    } else if (body) {
      out.push({ kind: "paragraph", text: body });
    }
    return;
  }
  const companyParts = splitCompanyMentions(body, opts);
  const hasCompanyBlocks = companyParts.some((p) => p.kind === "company");
  if (hasCompanyBlocks) {
    if (shouldEmitSectionTitle(title, stripAnalysisPrefix)) {
      out.push({ kind: "section", title });
    }
    out.push(...companyParts);
  } else if (shouldEmitSectionTitle(title, stripAnalysisPrefix)) {
    out.push({ kind: "section", title, body });
  } else if (body) {
    out.push(...companyParts);
  }
}

/** 公司名是否为新主体句首（非句中对比引用） */
function isCompanySubjectStart(text: string, index: number): boolean {
  if (index === 0) return true;
  let i = index - 1;
  while (i >= 0 && /\s/.test(text[i]!)) i -= 1;
  if (i < 0) return true;
  return /[。；！？\n]/.test(text[i]!);
}

/** 按文中公司名出现位置切分为主体块（同公司多次出现合并） */
function splitCompanyMentions(text: string, opts: FormatNarrativeOptions): NarrativePart[] {
  const labels = [...narrativeLabels(opts)].sort((a, b) => b.length - a.length);
  type Hit = { index: number; company: string; len: number };
  const hits: Hit[] = [];

  for (const label of labels) {
    let start = 0;
    while (start < text.length) {
      const idx = text.indexOf(label, start);
      if (idx === -1) break;
      if (!isCompanySubjectStart(text, idx)) {
        start = idx + label.length;
        continue;
      }
      const overlaps = hits.some((h) => idx >= h.index && idx < h.index + h.len);
      if (!overlaps) hits.push({ index: idx, company: label, len: label.length });
      start = idx + label.length;
    }
  }

  hits.sort((a, b) => a.index - b.index);

  if (hits.length < 2) {
    return splitCompanySentences(text, opts);
  }

  const parts: NarrativePart[] = [];
  const lead = text.slice(0, hits[0].index).trim();
  if (lead) parts.push({ kind: "paragraph", text: lead });

  const companyChunks = new Map<string, string[]>();
  for (let i = 0; i < hits.length; i += 1) {
    const start = hits[i].index;
    const end = hits[i + 1]?.index ?? text.length;
    const chunk = text.slice(start, end).trim();
    const company = hits[i].company;
    const body = chunk.slice(company.length).trim().replace(/^[，,：:\s]+/, "");
    const sentence = body ? `${body}` : "";
    if (!sentence) continue;
    const prev = companyChunks.get(company) ?? [];
    prev.push(sentence);
    companyChunks.set(company, prev);
  }

  for (const [company, sentences] of companyChunks) {
    parts.push({ kind: "company", company, text: sentences.join(" ") });
  }

  return parts.length ? parts : [{ kind: "paragraph", text: text.trim() }];
}

/** 按公司名切分长段落（句首或句号后接公司名） */
function splitCompanySentences(text: string, opts: FormatNarrativeOptions): NarrativePart[] {
  const labels = narrativeLabels(opts);
  const pattern = new RegExp(
    `(?<=[。；]|^)\\s*(${labels.map((n) => n.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`,
    "g",
  );
  const hits: { index: number; company: string }[] = [];
  let m: RegExpExecArray | null;
  while ((m = pattern.exec(text)) !== null) {
    hits.push({ index: m.index, company: m[1] });
  }

  if (hits.length < 2) return [{ kind: "paragraph", text: text.trim() }];

  const parts: NarrativePart[] = [];
  const lead = text.slice(0, hits[0].index).trim();
  if (lead) parts.push({ kind: "paragraph", text: lead });

  for (let i = 0; i < hits.length; i += 1) {
    const start = hits[i].index;
    const end = hits[i + 1]?.index ?? text.length;
    const chunk = text.slice(start, end).trim();
    const company = hits[i].company;
    const body = chunk.slice(company.length).trim().replace(/^[，,：:\s]+/, "");
    if (body) parts.push({ kind: "company", company, text: body });
  }
  return parts;
}

/** 将 MD 叙事拆为段落 / 小标题 / 分 company 块 */
export function formatNarrative(
  markdown: string,
  opts: FormatNarrativeOptions = {},
): NarrativePart[] {
  const splitCompanies = opts.splitCompanies !== false;
  const stripAnalysisPrefix = opts.stripAnalysisPrefix === true;
  const raw = markdown.trim();
  if (!raw) return [];

  const chunks = raw.split(/\n\n+/);
  const out: NarrativePart[] = [];

  for (const chunk of chunks) {
    const t = chunk.trim();
    if (!t) continue;

    const numbered = t.match(/^\(\d+\)/);
    if (numbered && out.length > 0 && out[out.length - 1].kind === "list") {
      (out[out.length - 1] as { kind: "list"; items: string[] }).items.push(t);
      continue;
    }

    if (/^\(\d+\)/.test(t)) {
      out.push({ kind: "list", items: [t] });
      continue;
    }

    const boldLead = t.match(/^\*\*([^*]+)\*\*([\s\S]*)$/);
    if (boldLead) {
      const title = boldLead[1].trim();
      const rest = boldLead[2].trim();
      if (!rest) {
        if (shouldEmitSectionTitle(title, stripAnalysisPrefix)) {
          out.push({ kind: "section", title });
        } else if (stripAnalysisPrefix && isAnalysisTitle(title)) {
          const cleaned = title.replace(/^分析——/, "").trim();
          if (cleaned) out.push({ kind: "paragraph", text: cleaned });
        }
      } else if (stripAnalysisPrefix && isAnalysisTitle(title)) {
        appendSectionBody(out, "", rest, opts);
      } else {
        appendSectionBody(out, title, rest, opts);
      }
      continue;
    }

    if (splitCompanies) {
      out.push(...splitCompanyMentions(t, opts));
    } else {
      out.push({ kind: "paragraph", text: t });
    }
  }

  return out;
}

/** 章节 lead 仅取首段摘要，避免整屏文字 */
export function narrativeLeadExcerpt(markdown: string, maxLen = 160): string {
  const parts = formatNarrative(markdown);
  const first = parts.find((p) => p.kind === "paragraph" || p.kind === "section");
  if (!first) return markdown.slice(0, maxLen);
  const text =
    first.kind === "section"
      ? first.body ?? first.title
      : first.kind === "paragraph"
        ? first.text
        : "";
  if (text.length <= maxLen) return text;
  return `${text.slice(0, maxLen).replace(/\s+\S*$/, "")}…`;
}

/** 按加粗小标题过滤叙事块（保留/排除） */
export function filterNarrativeBySectionTitles(
  markdown: string,
  opts: { include?: RegExp[]; exclude?: RegExp[] },
): string {
  const raw = markdown.trim();
  if (!raw) return "";

  const kept: string[] = [];
  let active = opts.include?.length ? false : true;

  for (const chunk of raw.split(/\n\n+/)) {
    const t = chunk.trim();
    if (!t) continue;

    const titleOnly = t.match(/^\*\*([^*]+)\*\*$/);
    const titleInline = t.match(/^\*\*([^*]+)\*\*\s+([\s\S]+)$/);

    if (titleOnly || titleInline) {
      const title = (titleOnly?.[1] ?? titleInline![1]).trim();
      if (opts.include?.length) {
        active = opts.include.some((p) => p.test(title));
      } else if (opts.exclude?.length) {
        active = !opts.exclude.some((p) => p.test(title));
      }
      if (active) kept.push(t);
      continue;
    }

    if (active) kept.push(t);
  }

  return kept.join("\n\n");
}
