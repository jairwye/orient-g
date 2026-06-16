import { buildSubjectAnalysisGroups, detectCompanyInTitle } from "./balance_subject_analysis";
import type { AnalystInsight, InsightTone } from "./finance_analysis";

export type TopicBullet = {
  text: string;
  tone?: InsightTone;
  tag?: string;
};

export type TopicAnalysisGroup = {
  /** 蓝本 **加粗小标题** 原文（含「分析——」等前缀） */
  title: string;
  /** 展示用短标题 */
  displayTitle: string;
  bullets: TopicBullet[];
};

export type TopicSection = {
  title: string;
  body: string;
};

export function displayTopicTitle(title: string): string {
  return title.replace(/^分析——/, "").replace(/[。.]+$/g, "").trim() || title;
}

/** 按蓝本 **小标题** 切分叙事块 */
export function splitMarkdownByBoldTitles(markdown: string): TopicSection[] {
  const raw = markdown.trim();
  if (!raw) return [];

  const sections: TopicSection[] = [];
  let currentTitle = "";
  let currentBody: string[] = [];

  const flush = () => {
    if (!currentTitle && !currentBody.length) return;
    sections.push({ title: currentTitle, body: currentBody.join("\n\n").trim() });
    currentTitle = "";
    currentBody = [];
  };

  for (const chunk of raw.split(/\n\n+/)) {
    const t = chunk.trim();
    if (!t) continue;

    const titleOnly = t.match(/^\*\*([^*]+)\*\*$/);
    const titleInline = t.match(/^\*\*([^*]+)\*\*\s+([\s\S]+)$/);

    if (titleOnly) {
      flush();
      currentTitle = titleOnly[1].trim();
    } else if (titleInline) {
      flush();
      currentTitle = titleInline[1].trim();
      currentBody.push(titleInline[2].trim());
    } else if (!currentTitle) {
      currentTitle = t;
    } else {
      currentBody.push(t);
    }
  }
  flush();

  return sections.filter((s) => s.title || s.body);
}

function narrativeBullets(body: string, sectionTitle: string): TopicBullet[] {
  if (!body.trim()) return [];
  const titleCo = detectCompanyInTitle(sectionTitle);
  const groups = buildSubjectAnalysisGroups(body, []);
  const bullets: TopicBullet[] = [];
  for (const g of groups) {
    for (const b of g.bullets) {
      let text: string;
      if (g.company === "综合观察" && titleCo) {
        text = `${titleCo}：${b.text}`;
      } else if (g.company === "综合观察") {
        text = b.text;
      } else {
        text = `${g.company}：${b.text}`;
      }
      bullets.push({ text, tone: b.tone, tag: b.tag });
    }
  }
  return bullets;
}

function insightToBullet(ins: AnalystInsight): TopicBullet {
  const text = ins.detail ? `${ins.headline}。${ins.detail}` : ins.headline;
  return { text, tone: ins.tone, tag: ins.label };
}

function insightMatchesTopic(ins: AnalystInsight, topicTitle: string): boolean {
  const topic = displayTopicTitle(topicTitle);
  const hay = `${ins.label} ${ins.headline} ${ins.detail ?? ""}`;

  if (/ROE|驱动力|杜邦/.test(topic)) {
    return /ROE|杜邦|亏损|资产效率|周转.*领先|驱动/.test(hay);
  }
  if (/权益乘数|杠杆/.test(topic)) {
    return /杠杆|权益乘数/.test(hay);
  }
  if (/净现金/.test(topic)) {
    return /净现金|短借/.test(hay);
  }
  if (/流动比率/.test(topic)) {
    return /流动比率|短期偿债|速动/.test(hay);
  }
  if (/应收/.test(topic)) {
    return /应收|账龄/.test(hay);
  }
  return false;
}

function assignInsightTopic(ins: AnalystInsight, sections: TopicSection[]): string | null {
  for (const s of sections) {
    if (s.title && insightMatchesTopic(ins, s.title)) return s.title;
  }
  const hay = `${ins.label} ${ins.headline}`;
  if (/ROE|杜邦|亏损|资产效率/.test(hay)) {
    return sections.find((s) => /ROE|驱动力/.test(displayTopicTitle(s.title)))?.title ?? null;
  }
  if (/净现金|短借/.test(hay)) {
    return sections.find((s) => /净现金/.test(s.title))?.title ?? null;
  }
  if (/流动比率|短期偿债/.test(hay)) {
    return sections.find((s) => /流动比率/.test(s.title))?.title ?? null;
  }
  if (/应收/.test(hay)) {
    return sections.find((s) => /应收/.test(s.title))?.title ?? null;
  }
  return sections[0]?.title ?? null;
}

/** 按蓝本 **小标题** 合并叙事与分析师洞察 */
export function buildTopicAnalysisGroups(
  markdown: string,
  insights: AnalystInsight[],
): TopicAnalysisGroup[] {
  const sections = splitMarkdownByBoldTitles(markdown);
  if (!sections.length && !insights.length) return [];

  const narrativeBuckets = new Map<string, TopicBullet[]>();
  const insightBuckets = new Map<string, TopicBullet[]>();
  const ensureN = (title: string) => {
    if (!narrativeBuckets.has(title)) narrativeBuckets.set(title, []);
    return narrativeBuckets.get(title)!;
  };
  const ensureI = (title: string) => {
    if (!insightBuckets.has(title)) insightBuckets.set(title, []);
    return insightBuckets.get(title)!;
  };

  for (const section of sections) {
    const key = section.title || "分析";
    for (const b of narrativeBullets(section.body, section.title)) {
      ensureN(key).push(b);
    }
  }

  const assigned = new Set<AnalystInsight>();
  for (const ins of insights) {
    const key = assignInsightTopic(ins, sections);
    if (key) {
      ensureI(key).push(insightToBullet(ins));
      assigned.add(ins);
    }
  }

  for (const ins of insights) {
    if (assigned.has(ins)) continue;
    const fallback = sections[0]?.title ?? "分析";
    ensureI(fallback).push(insightToBullet(ins));
  }

  const order = sections.map((s) => s.title || "分析");
  const seen = new Set<string>();
  const titles = [...order, ...narrativeBuckets.keys(), ...insightBuckets.keys()].filter((t) => {
    if (seen.has(t)) return false;
    const count = (narrativeBuckets.get(t)?.length ?? 0) + (insightBuckets.get(t)?.length ?? 0);
    if (!count) return false;
    seen.add(t);
    return true;
  });

  return titles.map((title) => ({
    title,
    displayTitle: displayTopicTitle(title),
    bullets: [...(insightBuckets.get(title) ?? []), ...(narrativeBuckets.get(title) ?? [])],
  }));
}
