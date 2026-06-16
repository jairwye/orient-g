import { colToLabel, COMPANY_COLS } from "./companies";

export type NarrativePart =
  | { kind: "section"; title: string; body?: string }
  | { kind: "company"; company: string; text: string }
  | { kind: "paragraph"; text: string }
  | { kind: "list"; items: string[] };

const COMPANY_LABELS = COMPANY_COLS.map((c) => colToLabel(c));

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
};

function isAnalysisTitle(title: string): boolean {
  return /^分析/.test(title.trim());
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
  splitCompanies: boolean,
  stripAnalysisPrefix = false,
) {
  const numbered = splitInlineNumberedItems(body);
  if (numbered) {
    if (shouldEmitSectionTitle(title, stripAnalysisPrefix)) {
      out.push({ kind: "section", title });
    }
    out.push(...numbered);
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
  const companyParts = splitCompanyMentions(body);
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

/** 按文中公司名出现位置切分为主体块（同公司多次出现合并） */
function splitCompanyMentions(text: string): NarrativePart[] {
  const labels = [...COMPANY_LABELS].sort((a, b) => b.length - a.length);
  type Hit = { index: number; company: string; len: number };
  const hits: Hit[] = [];

  for (const label of labels) {
    let start = 0;
    while (start < text.length) {
      const idx = text.indexOf(label, start);
      if (idx === -1) break;
      const overlaps = hits.some((h) => idx >= h.index && idx < h.index + h.len);
      if (!overlaps) hits.push({ index: idx, company: label, len: label.length });
      start = idx + label.length;
    }
  }

  hits.sort((a, b) => a.index - b.index);

  if (hits.length < 2) {
    return splitCompanySentences(text);
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
function splitCompanySentences(text: string): NarrativePart[] {
  const pattern = new RegExp(
    `(?<=[。；]|^)\\s*(${COMPANY_LABELS.map((n) => n.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`,
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
        appendSectionBody(out, "", rest, splitCompanies, stripAnalysisPrefix);
      } else {
        appendSectionBody(out, title, rest, splitCompanies, stripAnalysisPrefix);
      }
      continue;
    }

    if (splitCompanies) {
      out.push(...splitCompanyMentions(t));
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
