/**
 * 与经营数据展示页（BusinessDashboard）图表系列一致的颜色 token。
 * 其它页面（如知识库、Agent 顶栏）如需视觉对齐，请从这里引用，避免各处硬编码分叉。
 *
 * UI 变更流程：先更新 specs/ui/*.md → Read ~/.cursor/skills/frontend-design/SKILL.md
 *（Orient-G 约束节）→ 再改 frontend/（见 .cursor/rules/frontend-ui-design.mdc）。
 */
export const BUSINESS_CHART_COLORS = {
  current: "#2563eb",
  previous: "#3f3f46",
  actual: "#22c55e",
  target: "#3f3f46",
  lastYear: "#52525b",
} as const;

/**
 * Agent 页 / 历史 Agent 会话：与经营数据图表「当期」(#2563eb) 对齐的 Tailwind 类。
 * 与 AiAvatar、用户气泡（BUSINESS_CHART_COLORS.current）同一色系。
 */
export const AGENT_CHART_ACCENT_CLASS = {
  icon: "text-blue-600",
  iconMuted: "text-blue-600/65",
  headerBar: "border-b border-blue-900/45 bg-blue-950/30",
  headerTitle: "font-medium text-zinc-100",
  headerDesc: "text-xs text-zinc-500",
  modeGroup: "border border-blue-900/50 bg-zinc-950/40",
  modeActive: "bg-blue-600/30 text-blue-100",
  modeIdle: "text-zinc-500 hover:bg-blue-950/40 hover:text-blue-100/90",
  streamStatusBorder: "border-l-2 border-blue-600/45",
} as const;

/**
 * 正向 / 成功 / 实际值：与图表 actual（#22c55e，Tailwind green-500）对齐。
 * 用于 Excel 解析附件、上传成功提示、工作流选中等。
 */
export const CHART_POSITIVE_CLASS = {
  text: "text-green-500",
  textMuted: "text-green-500/90",
  icon: "text-green-500/90",
  attachmentBorder: "border-green-900/50",
  attachmentBg: "bg-green-950/20",
  progressBar: "bg-green-500/80",
  chipActive: "border-green-800/60 bg-green-950/25 text-green-100",
  statusText: "text-green-500",
  statusBg: "bg-green-500",
  resultBox: "text-green-500 bg-green-950/30",
  bannerText: "text-green-500/80",
  toastBorder: "border-green-800/50",
  toastBg: "bg-green-950/90",
  toastTitle: "text-green-200",
  toastMessage: "text-green-300/80",
} as const;

/**
 * 工作流「开发中」：与图表当期 blue-600（#2563eb）同色系。
 */
export const WORKFLOW_WIP_CLASS = {
  listRowBorder: "border border-dashed border-blue-900/45 bg-blue-950/15 hover:bg-blue-950/25",
  listTitle: "text-zinc-400",
  badge:
    "rounded border border-blue-600/35 bg-blue-600/10 px-1.5 py-0.5 text-[10px] font-medium leading-none text-blue-400/95",
  chipBorder: "border border-dashed border-blue-900/50 text-zinc-400",
  chipBadge: "rounded bg-blue-600/15 px-1 py-px text-[10px] font-medium leading-none text-blue-400/90",
  pageBanner:
    "flex flex-wrap items-center gap-2 rounded-lg border border-blue-900/45 bg-blue-950/25 px-3 py-2 text-xs text-blue-200/90",
  cardBorder:
    "border border-dashed border-blue-900/45 bg-blue-950/15 hover:border-blue-800/55 hover:bg-blue-950/25",
} as const;
