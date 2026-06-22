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
  const dashParts = title.split(TOPIC_DASH).map((s) => s.trim()).filter(Boolean);
  if (dashParts.length >= 2) {
    const topic = dashParts[0]!;
    const lead = dashParts.slice(1).join("");
    const body = [lead, rest].filter(Boolean).join(" ").trim();
    return body ? { topic, body } : null;
  }
  const topic = title.replace(/[。：:.]+$/g, "").trim();
  const body = rest.trim();
  if (!topic || !body) return null;
  return { topic, body };
}

/** sec-09-11 简要分析：按 snapshot 中 zq / la 展示名拆分 */
function splitBriefAnalysisByCompany(
  body: string,
  snapshot?: CompetitorReportSnapshot,
): SubjectAnalysisGroup[] {
  const text = body.trim();
  if (!text) return [];

  const zqLabel = snapshot?.companies.find((c) => c.id === "zq")?.label?.trim();
  const laLabel = snapshot?.companies.find((c) => c.id === "la")?.label?.trim();
  const groups: SubjectAnalysisGroup[] = [];

  if (zqLabel) {
    const zqIdx = text.indexOf(zqLabel);
    if (zqIdx >= 0) {
      const laIdx = laLabel ? text.indexOf(laLabel) : -1;
      const end = laIdx > zqIdx ? laIdx : text.length;
      groups.push({
        company: zqLabel,
        colKey: colKeyForDisplayLabel(zqLabel, snapshot),
        bullets: [{ text: text.slice(zqIdx, end).trim() }],
      });
    }
  }

  if (laLabel) {
    const laIdx = text.indexOf(laLabel);
    if (laIdx >= 0) {
      let laText = text.slice(laIdx);
      const abroadIdx = laText.indexOf("境外版本");
      if (abroadIdx > 0) laText = laText.slice(0, abroadIdx).trim();
      groups.push({
        company: laLabel,
        colKey: colKeyForDisplayLabel(laLabel, snapshot),
        bullets: [{ text: laText.trim() }],
      });
    }
  }

  if (groups.length) return groups;
  return splitByCompany(body, snapshot);
}

function isBriefAnalysisTopic(topic: string): boolean {
  return topic === "简要分析" || topic.startsWith("简要分析");
}

function isGameNameMappingTopic(topic: string): boolean {
  return topic === "游戏名称对应" || topic.startsWith("游戏名称对应");
}

function isRegionDistributionTopic(topic: string): boolean {
  return topic === "发行地区" || topic.startsWith("发行地区");
}

function isProductCountTopic(topic: string): boolean {
  return topic.startsWith("产品数量");
}

/** 产品数量：按句引用蓝本，删去 > 排名分隔符，不按公司拆行 */
function splitProductCount(body: string): SubjectAnalysisGroup[] {
  let text = body.trim();
  const subtitle = text.match(/^[^。；]{2,30}[。；]\s*/);
  if (subtitle && !/款|互娱|世界|掌趣|塔人|像素|绿岸|春秋|飞扬|可比/.test(subtitle[0]!)) {
    text = text.slice(subtitle[0].length).trim();
  }
  const sentences = text.split(/(?<=[。；!！?？])\s*/).filter((s) => s.trim());
  const strip = (s: string) => s.replace(/>/g, "");
  if (!sentences.length) {
    return [{ company: "", colKey: "", bullets: [{ text: strip(text) }] }];
  }
  return sentences.map((s) => ({
    company: "",
    colKey: "",
    bullets: [{ text: strip(s.trim()) }],
  }));
}

/** 游戏名称对应：蓝本原文整段引用，不按公司拆行 */
function splitGameNameMapping(body: string): SubjectAnalysisGroup[] {
  const text = body.trim();
  if (!text) return [];
  return [{ company: "", colKey: "", bullets: [{ text }] }];
}

/** 发行地区：连续两公司名以「和」连接时合并为一行，其余按主体分行 */
function regionCompanyBlocks(
  sent: string,
  labelsByLength: string[],
): Array<{ label: string; startIndex: number }> {
  type Hit = { label: string; index: number };
  const hits: Hit[] = [];
  for (const label of labelsByLength) {
    let start = 0;
    while (start < sent.length) {
      const idx = sent.indexOf(label, start);
      if (idx === -1) break;
      const overlaps = hits.some((h) => idx >= h.index && idx < h.index + h.label.length);
      if (!overlaps) hits.push({ label, index: idx });
      start = idx + label.length;
    }
  }
  hits.sort((a, b) => a.index - b.index);

  const blocks: Array<{ label: string; startIndex: number }> = [];
  let i = 0;
  while (i < hits.length) {
    const h = hits[i]!;
    const next = hits[i + 1];
    if (next && /^和\s*/.test(sent.slice(h.index + h.label.length, next.index))) {
      blocks.push({ label: "", startIndex: h.index });
      i += 2;
      continue;
    }
    blocks.push({ label: h.label, startIndex: h.index });
    i += 1;
  }
  return blocks;
}

function splitRegionSentence(
  sent: string,
  snapshot: CompetitorReportSnapshot | undefined,
  labelsByLength: string[],
): SubjectAnalysisGroup[] {
  const blocks = regionCompanyBlocks(sent, labelsByLength);
  if (!blocks.length) {
    return [{ company: "", colKey: "", bullets: [{ text: sent }] }];
  }

  return blocks.map((block, i) => {
    const end = blocks[i + 1]?.startIndex ?? sent.length;
    const fragment = sent.slice(block.startIndex, end).trim();
    const displayCo = block.label;
    let bulletText = fragment;
    if (displayCo && fragment.startsWith(displayCo)) {
      bulletText =
        fragment.slice(displayCo.length).replace(/^[，,：:\s的]+/, "").trim() || fragment;
    }
    return {
      company: displayCo,
      colKey: displayCo ? colKeyForDisplayLabel(displayCo, snapshot) : "",
      bullets: [{ text: displayCo ? bulletText : fragment }],
    };
  });
}

function splitRegionDistribution(
  body: string,
  snapshot?: CompetitorReportSnapshot,
): SubjectAnalysisGroup[] {
  let text = body.trim();
  const subtitle = text.match(/^[^。；]{2,30}[。；]\s*/);
  if (subtitle) {
    const hasCompany = getCompanyContext(snapshot).labelsByLength.some(
      (l) => l.length >= 2 && subtitle[0]!.includes(l),
    );
    if (!hasCompany) text = text.slice(subtitle[0]!.length).trim();
  }
  const labelsByLength = [...getCompanyContext(snapshot).labelsByLength];
  const sentences = text.split(/(?<=[。；!！?？])\s*/).filter((s) => s.trim());
  if (!sentences.length) {
    return [{ company: "", colKey: "", bullets: [{ text: body.trim() }] }];
  }
  return sentences.flatMap((s) => splitRegionSentence(s.trim(), snapshot, labelsByLength));
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

    let subjects: SubjectAnalysisGroup[];
    if (isBriefAnalysisTopic(parsed.topic)) {
      subjects = splitBriefAnalysisByCompany(parsed.body, snapshot);
    } else if (isGameNameMappingTopic(parsed.topic)) {
      subjects = splitGameNameMapping(parsed.body);
    } else if (isRegionDistributionTopic(parsed.topic)) {
      subjects = splitRegionDistribution(parsed.body, snapshot);
    } else if (isProductCountTopic(parsed.topic)) {
      subjects = splitProductCount(parsed.body);
    } else {
      subjects = splitByCompany(parsed.body, snapshot);
    }
    if (subjects.length) out.push({ topic: parsed.topic, subjects });
  }

  return out;
}

