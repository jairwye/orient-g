import { colKeyForDisplayLabel, getCompanyContext } from "./companies";
import type { CompetitorReportSnapshot } from "./types";
import type { SubjectAnalysisGroup } from "./balance_subject_analysis";

const TOPIC_DASH = /[—–\-－]/;

export type TopicSubjectGroup = {
  topic: string;
  subjects: SubjectAnalysisGroup[];
};

function findCompaniesInText(text: string, labelsByLength: string[]): string[] {
  type Hit = { label: string; index: number };
  const hits: Hit[] = [];
  for (const label of labelsByLength) {
    let start = 0;
    while (start < text.length) {
      const idx = text.indexOf(label, start);
      if (idx === -1) break;
      hits.push({ label, index: idx });
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

function pushFragment(
  bucket: Map<string, string[]>,
  order: string[],
  company: string,
  fragment: string,
) {
  const key = company || "行业综述";
  const text = fragment.trim();
  if (!text) return;
  if (!bucket.has(key)) {
    bucket.set(key, []);
    order.push(key);
  }
  bucket.get(key)!.push(text);
}

/** 按句拆分主体；同句多公司时按出现位置拆成多行 */
function splitByCompany(text: string, snapshot?: CompetitorReportSnapshot): SubjectAnalysisGroup[] {
  const ctx = getCompanyContext(snapshot);
  const labelsByLength = [...ctx.labelsByLength];
  const sentences = text.split(/(?<=[。；!！?？])\s*/).filter((s) => s.trim());
  if (!sentences.length) return [];

  const bucket = new Map<string, string[]>();
  const order: string[] = [];

  for (const sent of sentences) {
    const companies = findCompaniesInText(sent, labelsByLength);
    if (companies.length <= 1) {
      pushFragment(bucket, order, companies[0] ?? "行业综述", sent);
      continue;
    }
    for (let i = 0; i < companies.length; i++) {
      const co = companies[i]!;
      const idx = sent.indexOf(co);
      if (idx === -1) continue;
      const nextCo = companies[i + 1];
      const end = nextCo ? sent.indexOf(nextCo, idx + co.length) : sent.length;
      let body = sent.slice(idx + co.length, end).trim();
      body = body.replace(/^[，,：:\s的]+/, "");
      pushFragment(bucket, order, co, body || sent.slice(idx, end).trim());
    }
  }

  if (!order.length && text.trim()) {
    return [{ company: "行业综述", colKey: "", bullets: [{ text: text.trim() }] }];
  }

  return order
    .map((company) => ({
      company,
      colKey: colKeyForDisplayLabel(company, snapshot),
      bullets: (bucket.get(company) ?? []).map((t) => ({ text: t })),
    }))
    .filter((g) => g.bullets.length > 0);
}

function parseTopicChunk(title: string, rest: string): { topic: string; body: string } | null {
  const dash = title.split(TOPIC_DASH);
  if (dash.length >= 2) {
    const topic = dash[0]!.trim();
    const lead = dash.slice(1).join("—").trim();
    const body = [lead, rest].filter(Boolean).join(" ").trim();
    return body ? { topic, body } : null;
  }
  const topic = title.replace(/[。：:.]+$/g, "").trim();
  const body = rest.trim();
  if (!topic || !body) return null;
  return { topic, body };
}

/** 账龄、运营产品、主要游戏等：主题卡片内按公司分行 */
export function buildTopicSubjectGroups(
  markdown: string,
  snapshot?: CompetitorReportSnapshot,
): TopicSubjectGroup[] {
  const out: TopicSubjectGroup[] = [];
  const raw = markdown.trim();
  if (!raw) return out;

  for (const chunk of raw.split(/\n\n+/)) {
    const t = chunk.trim();
    if (!t || t.startsWith("###") || t.startsWith(">")) continue;
    if (/^分析|^总结/.test(t.replace(/^\*\*([^*]+)\*\*/, "$1"))) continue;

    const bold = t.match(/^\*\*([^*]+)\*\*\s*([\s\S]*)$/);
    if (!bold) continue;

    const parsed = parseTopicChunk(bold[1].trim(), bold[2].trim());
    if (!parsed) continue;
    if (/^分析——/.test(parsed.topic) && !TOPIC_DASH.test(bold[1].replace(/^分析——/, ""))) continue;

    const subjects = splitByCompany(parsed.body, snapshot);
    if (subjects.length) out.push({ topic: parsed.topic, subjects });
  }

  return out;
}

