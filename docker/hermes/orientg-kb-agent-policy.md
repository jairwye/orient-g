# Hermes Agent：Orient-G 知识库任务策略（运维粘贴用）

将下列要点加入 Hermes `config.yaml` 的 agent 系统说明，或与 Gateway 注入的 `orientg_tool_policy` 保持一致。

## Tier 1（`hermes_lite`）知识库问答

- **仅**使用 `orientg_kb_*` MCP 获取与引用证据（`orientg_kb_ask`、`orientg_kb_list` 等）。
- **禁止**使用 `terminal` / shell 读取本地路径、临时文件或编造 doc 内容充当答案。
- **允许且鼓励**使用 `orientg_kb_ask` / `orientg_kb_list` 等 `orientg_kb_*` MCP（禁用 terminal **不等于**禁用 KB 工具）。
- **禁止**依赖 `skill_view` 替代 KB 检索（产品 Skill 由 Orient-G 网关注入，非 Hermes 内置 skill）。
- 补检索次数受 Gateway `orientg_kb_ask_budget` 限制；超额调用将被 `denied`。

## Tier 0（快速模式）

浏览器走 Orient-G **本地综合**，不启动 Hermes，无 terminal 风险。

## Orient-G 自动补检索（Tier 1 / 条件 Tier 2）

当 **Tier 1（标准）** Hermes 在 breakdown/compare 任务中**未调用** `orientg_kb_ask` 时，Orient-G 网关会在流式 `done` 前自动执行定向补检索（最多 5 次 `orientg_kb_ask`）并用证据约束重新综合答案（SSE：`replace_reply`）。

**Tier 2（深度）** 默认以 Hermes Runs 终稿为主；但当 Hermes **未调 MCP** 且终稿缺分项、含估算、分析师报告过短等（见 `hermes_reply_needs_breakdown_revise`）时，网关**同样**可触发补检索 + 本地修订，**非**整篇无脑覆盖 Hermes 原文（`choose_supplemental_reply` 择优）。

## Tier 2（深度 / 写库）

- **知识库问答**仍仅通过 `orientg_kb_*` MCP 取证与写库；**禁止** `terminal` / shell / curl / loopback 调 Orient-G API。
- 写库须前端 **深度 + 写库开关**（`allow_kb_write=true`），且 MCP 写操作绑定用户 `kb_scope` 内 `folder_id`。
- 深度编排可有多轮 MCP；产物须 `orientg_kb_import_artifact` 落入选定文件夹，不得写 Hermes 工作区临时文件充当 KB 答案。

详见项目根 [docs/hermes.md](../../docs/hermes.md) 与 [specs/plans/1.2.3.b-acceptance-tests.md](../../specs/plans/1.2.3.b-acceptance-tests.md)。
