import {
  buildSubjectAnalysisGroups,
  type SubjectAnalysisGroup,
  type SubjectBullet,
} from "./balance_subject_analysis";
import { formatNarrative } from "./narrative_format";

/** 蓝本叙事 → 按公司分主体卡片 */
export function buildSec09SubjectGroups(markdown: string): SubjectAnalysisGroup[] {
  if (!markdown.trim()) return [];
  return buildSubjectAnalysisGroups(markdown, []);
}

const TOPIC_DASH = /[—–\-－]/;

function pushTopic(buckets: Map<string, SubjectBullet[]>, order: string[], topic: string, text: string) {
  const t = topic.trim();
  const body = text.trim();
  if (!t || !body || /^分析|^总结/.test(t)) return;
  if (!buckets.has(t)) {
    buckets.set(t, []);
    order.push(t);
  }
  buckets.get(t)!.push({ text: body });
}

/** 账龄、运营产品等 **主题——** 叙事 → 分主题卡片 */
export function buildTopicAnalysisGroups(markdown: string): SubjectAnalysisGroup[] {
  const buckets = new Map<string, SubjectBullet[]>();
  const order: string[] = [];
  const raw = markdown.trim();
  if (!raw) return [];

  for (const chunk of raw.split(/\n\n+/)) {
    const t = chunk.trim();
    if (!t || t.startsWith("###") || t.startsWith(">")) continue;

    const bold = t.match(/^\*\*([^*]+)\*\*\s*([\s\S]*)$/);
    if (bold) {
      const title = bold[1].trim();
      const rest = bold[2].trim();
      if (/^分析|^总结/.test(title) && !TOPIC_DASH.test(title)) continue;
      const dash = title.split(TOPIC_DASH);
      if (dash.length >= 2) {
        const topic = dash[0]!.trim();
        const lead = dash.slice(1).join("—").trim();
        pushTopic(buckets, order, topic, lead ? `${lead} ${rest}`.trim() : rest);
      } else if (rest) {
        pushTopic(buckets, order, title, rest);
      }
      continue;
    }

    for (const part of formatNarrative(t, { splitCompanies: false, stripAnalysisPrefix: true })) {
      if (part.kind === "section" && part.body) {
        const title = part.title.trim();
        const dash = title.split(TOPIC_DASH);
        if (dash.length >= 2) {
          pushTopic(buckets, order, dash[0]!.trim(), part.body);
        }
      }
    }
  }

  return order.map((topic) => ({
    company: topic,
    colKey: "",
    bullets: buckets.get(topic)!,
  }));
}
