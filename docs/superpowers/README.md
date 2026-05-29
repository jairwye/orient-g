# Cursor Superpowers 插件（开发工作流）

本目录**仅**存放与 [Cursor Superpowers](https://github.com/cursor-public/superpowers) 插件相关的说明：技能调用约定、工作流提示、临时笔记等。

## 与 `specs/` 的分工（必须遵守）

| 内容类型 | 正确位置 |
|----------|----------|
| 产品规制、功能方案、UI baseline | [`specs/features/`](../specs/features/)、[`specs/ui/`](../specs/ui/) |
| 实施计划、TDD 任务拆解 | [`specs/plans/`](../specs/plans/) |
| Superpowers 插件怎么用、brainstorming 流程 | **本目录**（可选子目录 `notes/`） |

**禁止**在 `docs/superpowers/specs/` 或 `docs/superpowers/plans/` 新增 Orient-G 产品规制或实施计划。历史文件已迁出，仅保留一行重定向 stub。

## 入口

- 仓库规制总索引：[`specs/README.md`](../specs/README.md)
- Hermes 联调手册（非规制）：[`docs/hermes.md`](../hermes.md)
