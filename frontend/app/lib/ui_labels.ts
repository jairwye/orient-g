/** 页面展示文案：产品「Agent」能力统一称「智能体」（路由/API 标识仍为 agent）。 */

export const UI_AGENT = {
  label: "智能体",
  newSessionTitle: "新智能体对话",
  sessionFallbackTitle: "智能体对话",
  modeAriaLabel: "智能体模式",
  stopTaskTitle: "停止智能体任务",
  historyEmptyHint: "暂无历史（对话与智能体均保存在本机浏览器）。",
  skillLabel: "智能体技能",
  redirectMessage: "正在打开 AI 互动 · 智能体…",
} as const;

/** 历史会话标题兼容旧版「Agent」文案。 */
export function normalizeAgentDisplayText(text: string): string {
  return text
    .replace(/新 Agent 对话/g, UI_AGENT.newSessionTitle)
    .replace(/Agent 对话/g, UI_AGENT.sessionFallbackTitle)
    .replace(/\bAgent\b/g, UI_AGENT.label);
}
