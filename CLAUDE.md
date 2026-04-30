# Orient-G — AI 开发协作约定（CLAUDE.md）

本文件用于**开发协作阶段**（本仓库写代码、写方案、做 review/QA）的 AI 工作流约定，避免把 IDE 插件/第三方 skill 包与「Orient-G 产品侧 Agent Skill」混为一谈。

---

## 1) 两套“Skill”的边界（必须遵守）

### 1.1 产品侧 Agent Skill（交付物/运行时）

- **唯一登记入口**：`backend/data/agent_skills/manifest.json`
- **唯一指令体来源**：`backend/data/agent_skills/<skill_id>/SKILL.md`
- 任何“产品对内网用户可用的技能能力”必须遵守 `docs/skills-guidelines.md` 与《规则》中的：仅内网、本地化 AI、最小权限、可审计、证据引用、禁止编造、日志脱敏等要求。

### 1.2 开发机侧 Cursor 技能（仅开发者本机）

开发者可在本机 Cursor 使用第三方技能包/插件来提高开发效率，例如：

- Cursor Superpowers 插件（文档 `docs/superpowers/plans/` 中引用的 `superpowers:*` 工作流提示）
- gstack（`https://github.com/garrytan/gstack`）

**硬约束（gstack）：**

- gstack **不得**写入 `backend/data/agent_skills/manifest.json`
- gstack **不得**作为 Orient-G **交付物/运行时依赖**纳入发布产物、镜像或部署脚本
- gstack 仅允许作为**开发者本机 Cursor 工作流工具**使用

---

## 2) 数据与网络安全（开发机也必须遵守）

即便是“开发机侧工具”，也不得违反本仓库《规则》中对数据不外泄的要求：

- **禁止**将任何业务数据、内网 URL、账号/密码、token、Cookie、内部文档原文、数据库内容、上传文件内容等发送到外部第三方服务或外网模型。
- **允许**使用浏览器/抓取类能力时，仅限于**公开网页**或**已脱敏/可公开内容**；涉及内网系统页面、鉴权页面或敏感数据时，必须按团队安全流程处理。

---

## 3) gstack（开发机侧）使用提示（Windows）

你当前机器已采用如下约定：

- gstack 源码目录：`E:\Tools\gstack`
- Bun：`E:\Tools\bun\bin`（已加入用户 PATH）
- Playwright 浏览器缓存目录：`E:\Tools\playwright-browsers`

为避免 C 盘空间不足，使用 gstack 浏览器能力时建议固定设置：

- **Git Bash/WSL 环境变量**：`PLAYWRIGHT_BROWSERS_PATH=/e/Tools/playwright-browsers`

> 说明：Cursor 内的 MCP（如 chrome-devtools、playwright MCP）与 gstack 的 Playwright 运行时是不同层面的能力，可同时存在；本仓库默认更偏向“最小化工具面”，未必要启用所有 MCP。

---

## 4) 约定优先级

- 本文件只约束“开发协作工作流”。
- 任何与《规则》冲突之处，以《规则》为准。

