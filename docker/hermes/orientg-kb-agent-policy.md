# Hermes Agent：Orient-G 知识库任务策略（运维粘贴用）

将下列要点加入 Hermes `config.yaml` 的 agent 系统说明，或与 Gateway 注入的 `orientg_tool_policy` 保持一致。

## Tier 1（`hermes_lite`）知识库问答

- **仅**使用 `orientg_kb_*` MCP 获取与引用证据（`orientg_kb_ask`、`orientg_kb_list` 等）。
- **禁止**使用 `terminal` / shell 读取本地路径、临时文件或编造 doc 内容充当答案。
- **禁止**依赖 `skill_view` 替代 KB 检索（产品 Skill 由 Orient-G 网关注入，非 Hermes 内置 skill）。
- 补检索次数受 Gateway `orientg_kb_ask_budget` 限制；超额调用将被 `denied`。

## Tier 0（标准模式 pack 足够）

浏览器走 Orient-G **本地综合**，不启动 Hermes，无 terminal 风险。

## Tier 2（深度 / 写库）

允许完整工具环；写库须 `allow_kb_write=true` 且用户显式选择深度模式。

详见项目根 [docs/hermes.md](../../docs/hermes.md) 与 [specs/plans/1.2.3.b-acceptance-tests.md](../../specs/plans/1.2.3.b-acceptance-tests.md)。
