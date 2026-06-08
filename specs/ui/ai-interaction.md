# AI内网页 UI 规制（路由 `/ai-interaction`）

| 字段 | 值 |
|------|-----|
| **status** | `baseline` |
| **日期** | 2026-05-21 |
| **路由** | `/ai-interaction` |
| **实现主文件** | `frontend/app/ai-interaction/page.tsx` |
| **参考（非规制）** | [docs/reference/kimi-ui-reference.md](../../docs/reference/kimi-ui-reference.md) |

本文描述**当前已验收**的 UI 行为。后续改动须先更新本文再改代码；**默认不得改动圆角框相对视口的外边距与位置**（见 §3）。

---

## 1. 范围

- **包含**：左侧页内导航（新对话、**智能体**、工作空间、历史对话与会话列表）、右侧圆角主面板（对话 / 智能体 / 工作空间 Tab）、输入区、回到底部、模型名展示、消息气泡与内嵌图表。
- **不包含**：后端 `/api/ai-interaction/*` 契约（见 [`specs/api/api-contract.md`](../api/api-contract.md)）、产品 Agent Skill 正文（见 `backend/data/agent_skills/`）。

---

## 2. 信息架构

### 2.1 左侧栏（`md+` 显示，宽 `300px`）

| 区块 | 行为 |
|------|------|
| 标题 | `AI内网`，`text-2xl`，`pt-6 md:pt-8` |
| 新对话 | 左对齐按钮，`Plus` 图标 + 文案 |
| 智能体 | 可点击，`Bot` 图标；激活时图标色 `AGENT_CHART_ACCENT_CLASS.icon`（见 §5.1）；展示文案见 `frontend/app/lib/ui_labels.ts` |
| 工作空间 | 可点击，`Folder` 图标；激活时 `bg-zinc-800/60` |
| 历史对话 | **仅分组标题**（`History` 图标），不可当作会话项 |
| 会话列表 | 位于「历史对话」**之下**，见 §2.2 |

### 2.2 历史会话列表

- 外层缩进：`pl-7`（`historySessionsIndentClass`），表示从属于「历史对话」。
- 行内：`pl-3 pr-9`（`sessionRowClass`），激活/hover 底色**不得贴文字左沿**。
- 标题：`truncate`；附件 chip 最多展示 3 个。
- 切换会话：**不得**因 `updated_at` 将条目重排顶到列表最上（持久化原地更新）。
- **智能体会话行**：标题前 `Bot` 图标，`AGENT_CHART_ACCENT_CLASS.iconMuted`；默认标题「智能体对话」；历史 localStorage 中「Agent」文案经 `normalizeAgentDisplayText` 展示为「智能体」。

---

## 3. 右侧圆角主面板（位置与壳层）

> **冻结项**：下列外边距与视口高度为当前 baseline；调整对齐/截断时只改 §4、§5，不先改本节。

|  token | 类名 / 值 | 说明 |
|--------|-----------|------|
| 页面行高 | `h-[calc(100dvh)]` | 占满动态视口，不再 `100vh-64px` |
| 主列顶内边距 | `main`: `pt-0` | 不与侧栏重复 `pt-6` |
| 框外留白 | `mainPanelOuterPadClass`: `p-1 md:p-1.5` | 四周 4px / 6px |
| 圆角 | `rounded-xl`（12px） | 较 `rounded-2xl` 更小 |
| 框面 | `border-zinc-800/45` + `bg-zinc-900/25` | 单层底色，子区域不重复铺色 |
| 滚动条 | 全宽滚动容器 + `.chat-panel-scroll` | 贴在**框右缘**，非内容列中间 |

实现常量（须与代码同步）：

```text
chatPanelSurfaceClass, mainPanelFrameClass, mainPanelOuterPadClass
chatTitleSyncSpacerClass, chatScrollViewportClass, chatScrollAreaClass
chatContentInnerClass, chatMessagesStackClass, chatScrollToBottomBtnClass
```

---

## 4. 对话区：顶对齐与截断

### 4.1 与「AI内网」标题顶对齐

采用**固定顶区 + 下方滚动**（非在滚动区内用 `padding-top` 垫高）：

```
圆角框
├── 固定顶区 chatTitleSyncSpacerClass  h-5 / md:h-[1.625rem]  （无单独 background）
└── 滚动区 chatScrollAreaClass
    └── 内容列 chatContentInnerClass  max-w-3xl mx-auto
```

- 顶区高度 = 侧栏 `pt-6|pt-8` − 框外 `p-1|p-1.5` → **20px / 26px**。
- 圆角 `overflow-hidden` 只裁切顶区空白；**消息在矩形滚动口裁切**，避免在框物理上沿直接切断文字。
- 消息栈 **`pt-0`**（`chatMessagesStackClass`），首条顶对齐由顶区承担。

### 4.2 内容列与滚动

| 项 | 规制 |
|----|------|
| 内容列宽 | `max-w-3xl`，`px-5 md:px-6`，水平居中 |
| 长文本 | `[overflow-wrap:anywhere]`、`break-words` |
| `pre` / JSON | `max-w-full overflow-x-auto break-all` |
| 空态 | 垂直居中；不适用 §4.1 顶对齐（无历史消息） |
| 有消息时 | **无**消息区与输入区之间的横线 |

### 4.3 回到底部

- 圆形按钮，在滚动视口 `absolute bottom-3`。
- 水平：`right-[max(0.75rem,calc((100%-min(100%,48rem))/2))]`（内容列右缘，非页面居中）。
- 仅 `messages.length > 0` 且未在底部时显示。

---

## 5. 消息与配色

配色统一引用 `frontend/app/lib/business_chart_colors.ts` → `BUSINESS_CHART_COLORS`（与经营数据页一致）。

| 元素 | 规制 |
|------|------|
| 用户气泡 | 背景 `BUSINESS_CHART_COLORS.current`（`#2563eb`），文字 `#f4f4f5` |
| 助手气泡 | `border border-zinc-800 bg-zinc-900/50 text-zinc-200`，`rounded-2xl` |
| AI 头像 | `AiAvatar` `compact`（仅图标）；图标底 `current` 色 + `border-zinc-800` |
| 正向 / 成功 | `CHART_POSITIVE_CLASS`（`actual` / `#22c55e` / green-500）：Excel 附件、上传提示、工作流选中、大 PDF 完成态 |
| 内嵌图表 | `AiInlineChart` 主系列色与 `current` / `actual` 对齐 |
| 用户气泡宽 | `max-w-[85%]`，`min-w-0` |

### 5.1 智能体视图（`activeLeftView=agent`）

实现常量：`frontend/app/lib/business_chart_colors.ts` → `AGENT_CHART_ACCENT_CLASS`（与 `BUSINESS_CHART_COLORS.current` / `#2563eb` 对齐，**禁止** violet 或其它与经营数据页冲突的强调色）。

| 元素 | 规制 |
|------|------|
| 顶栏 | `headerBar`：`border-blue-900/45` + `bg-blue-950/30`；标题 `headerTitle`；说明 `headerDesc`（zinc 次级文案） |
| 模式切换 | 快速 / 标准 / 深度；容器 `modeGroup`；选中 `modeActive`，未选 `modeIdle`；请求体 `agent_mode` |
| 流式状态（助手气泡内） | 左边线 `streamStatusBorder`；文案 `text-zinc-500`；**不用**顶栏独立状态区 |
| 执行过程（Hermes） | 可折叠 `AgentTracePanel`（`w-full`，与正文同宽）；`status` / `tool` / `thinking` / `meta`；Agent 助手行 `assistantMessageRowClass(true)` 占满 `max-w-3xl` 内容列 |
| 侧栏 Agent 入口 | 激活时 Bot 图标 `icon` |

详见 [`specs/ui/1.2.3-agent-page.md`](1.2.3-agent-page.md)。

输入区：右下角展示当前 LLM 模型名（`/api/ai-interaction/models` + 响应 `llm_model`）；「+」等菜单**向上弹出**。

---

## 6. 工作空间 Tab

- 与对话共用 `mainPanelOuterPadClass` / `mainPanelFrameClass`。
- Tab：知识库、大 PDF 文档包、提示词、技能、工具、工作流。
- 工作空间内容区可滚动，类名含 `chat-panel-scroll`。

---

## 7. Evidence Pack（对话 / 智能体）

与 Agent 预检索同源（`retrieve_kb_for_chat` / `retrieve_and_answer`），后端响应可含 `evidence_pack` 摘要。

| 场景 | 展示位置 | 字段 |
|------|----------|------|
| **智能体** Tab，SSE `prefetch_done` | 执行过程时间线 | `agent_tier`、`evidence_pack`（`task_type`、`coverage_score`、`gaps`、`retrieval_queries`） |
| **对话** Tab，`read_mode=rag_pack` | 助手消息上方摘要条 | `ChatMessage.evidence_pack`（同结构） |

文案与解析：`frontend/app/ai-interaction/agentTraceUtils.ts`（`formatEvidencePackLine`、`parseAgentDoneMeta`）。类型：`types.ts` 中 `EvidencePackSummary`。

**非目标：** 不在气泡内展开全文 facet；详情仍靠 citations / 知识库跳转。

---

## 8. 验收清单

- [ ] 圆角框上下留白仍为 `p-1 / md:p-1.5`，未无意改回 `pt-6` 或 `100vh-64px`。
- [ ] 首条消息顶与侧栏「AI内网」标题顶对齐；上滚时不在框顶圆弧处切字。
- [ ] 滚动条在圆角框最右侧；内容列居中。
- [ ] 历史会话激活条底色在 `pl-7` 分组内，文字左侧有 `pl-3` 空隙。
- [ ] 用户/助手气泡色与 `BUSINESS_CHART_COLORS` 一致。
- [ ] Agent 顶栏 / 历史 Bot 图标 / 模式切换 / 流式左边线使用 `AGENT_CHART_ACCENT_CLASS`，无 violet 套系。
- [ ] 切换历史会话不重排列表顶。

---

## 9. 变更流程

1. 更新本文（含 status 与日期）。
2. Read `~/.cursor/skills/frontend-design/SKILL.md`（Orient-G 约束节）。
3. 改 `page.tsx` / 子组件；若对标 Kimi，只更新 `docs/reference/` 截图说明。
4. 若需调整 §3 冻结项，须在 PR/评审中**显式说明**。

---

## 10. 非目标

- 不在本规制内规定后端 RAG、会话持久化格式。
- 不要求与 Kimi 浅色主题一致（Orient-G 为 zinc 深色壳层）。
