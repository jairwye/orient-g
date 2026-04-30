# 术语：Agent Skill、Tool 与提示词资产（Orient-G）

本仓库在文档、规划与界面文案中出现的 **「Skill / 技能 / skills」**，默认指 **Agent Skills 生态**中有相对统一形态的能力单元（可登记、带元数据与指令体），而不是泛指「任意一段 prompt 或 JSON 配置」。

**外部参考（形态与目录习惯）**：

- [anthropics/skills](https://github.com/anthropics/skills)：公开示例与 `SKILL.md`（YAML frontmatter：`name`、`description`）+ 正文指令；并指向 [Agent Skills 标准](https://agentskills.io)。
- [openclaw/clawhub](https://github.com/openclaw/clawhub)：OpenClaw 的 **Skill Directory**，以可发现、可安装的 skill 包为组织方式。

---

## 1. Agent Skill（技能 / Agent Skill）

**定义**：一个**自包含、可登记**的能力包，至少具备：

| 要素 | 说明 |
| ---- | ---- |
| **元数据** | 机器可读的唯一 `name`（小写、连字符或项目约定）、人类可读的 `description`（说明做什么、何时启用）。 |
| **指令体** | 供 Agent 遵循的 Markdown 说明（示例、边界、输出形状等）。 |
| **标准载体（推荐）** | 与社区习惯对齐时，使用目录 + `SKILL.md`（frontmatter + 正文）；可附带只读资源（模板片段、字典等），**不得**引入未审计的任意远程拉取或公网依赖（见 [规则/规则.md](../规则/规则.md)）。 |

**在本项目中的实现关系**：Agent Skill 描述「做什么」；若涉及落库、ACL、调用 Ollama 等，由 **后端 Skill Handler**（如 `backend/services/skills/`）在运行时执行，并遵守 [docs/skills-guidelines.md](skills-guidelines.md)。

---

## 2. Tool（工具 / MCP 风格工具）

**定义**：通过 **JSON Schema 描述入参**、边界清晰的 **原子能力**（只读查询、受控渲染、受控转换等），由 **allow-list** 授权后供模型或编排层调用；形态上对齐 [Model Context Protocol - Tools](https://modelcontextprotocol.wiki/en/docs/concepts/tools) 的「name + description + inputSchema」实践。

**与 Agent Skill 的区分**：Tool 不负责完整业务叙事；**Agent Skill** 可编排多个 Tool 与其它步骤，并由 **Skill Handler** 对业务结果负责。

---

## 3. 提示词资产（Prompt 登记，非 Agent Skill）

**定义**：全站或某场景可复用的 **Prompt 设计条目**（如 System/User 摘要、固定句式、输出 JSON 约束说明），以稳定 **`prompt.*` ID**（或项目约定的 `prompt.*.v*`）登记；存放在 **AI 互动 → 工作空间 →「提示词」Tab** 的配置（当前为浏览器 `localStorage` JSON，后续可接后端），与 **Agent Skill** 分列，避免把「长 prompt」误称为 Skill。

**与成熟素材的关系**：可借鉴公开 **prompt 模板 / 话术 / 所谓 playbook 类** 素材；采纳后写入本条目的 `summary` / `body` 或并入某 Agent Skill 目录下的只读 `resources/*.md`，**对外交付形态**仍推荐统一为 **标准 Skill 目录**（若该段内容仅服务某一 Skill）。

---

## 4. 「Playbook」一词（内部别名，非行业标准）

**Playbook** 在通用英语里指「行动手册」，**不是**与 MCP、Agent Skills 同级的协议名。本仓库曾用其指「口径类配置」；现已**收敛**为：

- **优先使用**：**提示词资产**（`prompt.*`）+ **Agent Skill 目录资源**；
- **Playbook** 仅在少数文档或迁移说明中作为**内部别名**出现，新文档请避免单独成章与 Skill 并列。

---

## 5. 与界面文案的对应（约定）

| UI 文案 | 本术语 |
| ------- | ------ |
| 工作空间 → **技能** | **Agent Skill** 列表（及其实现状态）；配置编辑对应 Skill 注册表或 JSON 镜像。 |
| 工作空间 → **提示词** | **提示词资产**（`prompt.*`），全站/分场景 Prompt 设计登记。 |
| 工作空间 → **工具** | **MCP 风格 Tool** 列表与 allow-list。 |

---

## 6. 产品合规范围与开发机 Cursor 技能边界

本节与 [规则/规则.md](../规则/规则.md) 第四节、《协作开发指南》中「产品 Agent Skill」口径对齐，用于划清 **Orient-G 运行时登记技能** 与 **本机 Cursor 外挂技能**。

| 类别 | 含义 | 与《规则》中「本仓 / 内网 Agent Skill」的关系 |
| ---- | ---- | --------------------------------------------- |
| **产品 Agent Skill** | 仅 `backend/data/agent_skills/manifest.json` 所列 ID，及同目录下对应 `SKILL.md`；由后端注入 AI 互动等能力。 | **属于**合规登记范围；须满足本文第 1 节「标准载体」与 [skills-guidelines.md](skills-guidelines.md)。 |
| **开发机 Cursor 技能** | 例如 Cursor **Superpowers** 插件分发的技能（文档中 `superpowers:*` 类提示）、开发者自行安装的 **[gstack](https://github.com/garrytan/gstack)** 等；文件位于用户本机 `.cursor/` 等路径，**不在本仓库 manifest 中**。 | **不属于**产品登记技能；不按「本仓 manifest 技能包」审计，**但**使用者仍须遵守《规则》对数据不外泄、内网业务不违规走公网等要求。 |

**明确约定（gstack）**：gstack **不**写入 `backend/data/agent_skills/manifest.json`，**不**作为 Orient-G **交付物**或生产/内网运行时的依赖组件纳入发布清单；若需团队统一工作流，应通过**单独的内部安全与采购流程**处理，而非并入产品 Skill 注册表。

---

## 7. 文档维护

- 规划类文档（`规划/`）按仓库约定可不进 GitHub，但术语须与本文一致。
- 凡新建规划或改 UI 文案，涉及「技能 / 提示词 / 工具」时请先对照本文。
