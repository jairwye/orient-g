# Skill 编写通行规范（Orient-G）

本文件用于约束与统一本仓库中 **Agent Skill（技能）** 及其**运行时实现**的设计方式，保证安全、可审计、可回归、可继承。本文档 **进入 Git**，作为团队协作的共同口径。

**术语总表（须先读）**：[docs/agent-skills-glossary.md](agent-skills-glossary.md)。其中约定：本仓库所说的 **Skill / 技能** 对齐 [Agent Skills](https://agentskills.io) / [anthropics/skills](https://github.com/anthropics/skills) / [ClawHub](https://github.com/openclaw/clawhub) 等生态中「可登记、带元数据与指令体」的 **Agent Skill**；**Tool** 为 MCP 风格工具；**全站 Prompt 设计** 在 **AI 互动工作空间 →「提示词」Tab** 以 **`prompt.*` ID** 登记，与 Agent Skill 分列；成熟话术可吸收后写入该处或并入 Skill 目录 `resources/`。

## 1. Agent Skill 的定位与实现

- **Agent Skill（技能）**：对外是一个可发现、可描述、可版本化的能力包（推荐形态：目录 + `SKILL.md`，含 YAML `name`、`description` 与正文指令）；对内由 **Skill Handler** 实现具体 I/O、校验与落库。
- **Skill 是业务能力封装**：以稳定的输入/输出 schema 表达一个“可复用动作”，例如：生成项目核算表、生成合同台账草稿、生成流程文档等（与 Agent Skill 的 `description` 一致，并在 Handler 中落实契约）。
- **Tool 是基础能力**：例如 Docling 转换、MCP 只读查询、渲染等。
- Agent Skill 可以调用 Tool，但 **Skill Handler 必须对业务结果负责**（验证、落库、产出引用）。

## 2. 安全与合规（硬约束）

- **仅内网**：不得把业务数据发送到公网第三方服务。
- **LLM 仅走本地 Ollama**：如需模型推理，必须通过后端调用 `settings.ollama_url` 指向的 Ollama。
- **最小权限**：
  - 必须在执行前计算 ACL（例如 `compute_acl_scope()`）。
  - 写入目标集合必须属于 `writable_collection_ids`。
  - 对外返回必须做子集校验与越权拒绝。
- **禁止编造**：涉及金额、日期、条款、指标等信息，必须来源于证据（KB 文档 chunk / 表行 / 规则输入）。证据不足必须明确说明“不确定/缺少证据”。
- **不在响应中泄露敏感明文证据**：若需要引用，返回 citations（doc_id/chunk_id 或 table_id/row_key 等定位信息），不直接返回整段原文。

## 3. 输入/输出与版本化

- **每个 Agent Skill 必须有稳定业务 ID**（与 Handler、注册表、UI allow-list 一致）：推荐 `skill.<domain>.<name>.v<major>`，例如 `skill.project_accounting_table.v1`。**注意**：该 ID 与 `SKILL.md` frontmatter 的 `name` 应可一一映射（允许通过注册表显式映射）。
- **提示词资产不得使用 `skill.` 前缀**；请使用 `prompt.<domain>.<name>.v<major>` 等，见 [agent-skills-glossary.md](agent-skills-glossary.md)。
- **输入必须结构化**：即使用户以自然语言触发，也应在 Skill Handler 内转换为结构化输入并校验。
- **输出必须可审计/可回归**：
  - 返回 `ok`、`summary`（人类可读）、`citations[]`（可追溯）
  - 若产生落库产物，必须返回产物标识（如 `table_id`、`doc_id`、`contract_id`）

## 4. 落库与引用（推荐模式）

- **表类产物**：优先落库到 `kb_table_instances` + `kb_table_rows`，并写入：
  - `kb_resource_owner`（owner）
  - `kb_resource_collection_assignments`（归属集合）
- **文档类产物**：优先走 `kb_documents.upload_user_document` 体系，形成：
  - raw / archive(full.md/full.json) / kb(manifest + sections)
  - chunks（兼容检索）与向量（可选开关）

## 5. 工具调用（Tools）

- 必须受 **allow-list** 限制（用户未勾选/未允许的 tool 不得执行）。
- 默认只允许 **只读或受控副作用** 的工具；若有副作用（写库/写文件/发请求），必须：
  - 在实现中显式声明副作用范围
  - 失败可恢复（幂等或可重试）

## 6. LLM 使用规范（如需）

- **必须有系统约束提示词**：
  - 只能依据证据回答
  - 不确定要说明缺证据
  - 输出格式（如 JSON schema）必须校验
- **必须有护栏**：使用 `post_json_with_guard()`（熔断 + 并发信号量），避免系统雪崩。
- **证据上下文最小化**：只拼接必要片段（例如 chunk 文本截断、表行 JSON），避免把整库内容塞进 prompt。

## 7. 错误处理与可观测

- 可预期错误返回用户可读信息（400/403/429/503 等）。
- 关键路径写审计事件（建议）：attempt / deny / skill.run / tool.call / generate。
- 不要在日志里打印敏感明文（合同全文、用户上传原文、完整 prompt）。

## 8. 数据库结构变更（通行做法）

本仓库当前采用“启动时 `CREATE TABLE IF NOT EXISTS` + 少量 `ALTER TABLE IF NOT EXISTS`”的轻量迁移方式。

通行更安全做法（推荐逐步演进）：

- 使用 **迁移工具（如 Alembic）**：
  - 每次 schema 变更写一个版本化 migration 脚本
  - 上线前先在生产执行 migration
  - 应用启动不再隐式改 schema

在未引入 Alembic 前，本仓库建议：

- 每次 schema 变更都在 `docs/` 提供一份 **手工 SQL**（便于生产先执行再发版）
- 生产上线前备份数据库

## 9. 最小示例（参考）

- `backend/services/skills/project_accounting_table.py`：生成表实例并返回 citations

## 10. 开源社区示例（推荐直接对照抄结构）

在开源生态（以 [`anthropics/skills`](https://github.com/anthropics/skills) 为代表）里，**最通用、最容易被复用/二次封装**的技能，通常是“文件类型/工作流类型”技能，例如：

- `xlsx`：电子表读写/清洗/建模（对 FP&A 最贴近）
- `pdf`：PDF 摘要/抽取/结构化
- `docx`：Word 文档生成/改写
- `pptx`：演示文稿生成
- `webapp-testing`：Web 应用测试流程
- `mcp-builder`：生成/封装 MCP server
- `skill-creator`：生成技能目录骨架

其中最适合作为本仓库示例的是 **`xlsx`**（与“电子表数据解析闭环”一致）。它的 `SKILL.md` 结构非常规范：**YAML frontmatter（name/description/license）+ Requirements + 细分工作流 + 示例代码**。

参考原文（上游）：`https://raw.githubusercontent.com/anthropics/skills/main/skills/xlsx/SKILL.md`

### 10.1 关于“放完整版 + 中文翻译版”的结论（重要）

- **中文版 `SKILL.md` 能否生效**：在多数实现里，`SKILL.md` 的**正文只是 Markdown 指令文本**，语言不限（中文/英文都可以）。真正“会不会被加载/识别”，主要取决于解析器是否能正确解析 YAML frontmatter（`name`、`description` 等字段）与目录结构，而不是正文语言。  
  - **建议**：`name` 建议保持**稳定、可机器匹配**（短英文/拼音/slug 都行）；`description` 可用**中英双语**以提升触发命中；正文用中文更贴合团队。
- **为何不在本仓库“粘贴上游完整版”**：上游 `xlsx` 的 `SKILL.md` frontmatter 明确写了 `license: Proprietary. LICENSE.txt has complete terms`。即便你们是内部使用、非商用，**也不代表可以把“完整文本”复制进本仓库并提交 Git**（版权/许可风险与是否商用无必然关系）。  
  - **做法**：我们在文档里放**上游链接** + 放一份“按其结构与意图重写的中文版示例（我们自有版权）”，即可达到“示范写法”的目的，同时避免许可证纠纷。

### 10.2 上游原文（完整版）如何放置

在本仓库的 `docs/` 中，**仅保留链接**（以及最多少量节选用于说明结构），例如：

- 上游原文：`https://raw.githubusercontent.com/anthropics/skills/main/skills/xlsx/SKILL.md`

下面节选其开头（用于展示结构与写法；不要无脑照搬其“金融模型配色规范”等与本仓库不一致的约束）：

```md
---
name: xlsx
description: "Use this skill any time a spreadsheet file is the primary input or output. ..."
license: Proprietary. LICENSE.txt has complete terms
---

# Requirements for Outputs

## All Excel files

### Professional Font
- Use a consistent, professional font ...
```

将其迁移到本仓库时的改写建议：

- **ID 与前缀**：对外稳定 ID 用 `skill.<domain>.<name>.v1`（注册表/allow-list 用它）；`SKILL.md` frontmatter 的 `name` 可用短名（如 `data_parse_xlsx`）并在注册表里显式映射。
- **避免把“执行环境假设”写死**：上游 `xlsx` 假设有 LibreOffice 与 `scripts/recalc.py`；本仓库如果不提供该依赖，应删掉或改为“可选能力”。
- **把安全约束写清**：明确“不得把行级明细塞进 prompt / 不得落日志 / 只允许使用 allow-list tools”等（与本文件第 2、5、6 节一致）。

### 10.3 中文翻译版（可用于本仓库的“示例 Skill 文本”）

下面是一份“**按上游结构重写**、适配本仓库约束（内网/脱敏/allow-list/可审计）”的中文示例。注意：这是示例写法，不代表你们一定要实现其中提到的具体依赖（如 LibreOffice 重算）。

```md
---
name: data_parse_xlsx
description: "（中文）当用户的主要输入或输出是电子表（.xlsx/.xlsm/.csv/.tsv）时使用此技能：读取/清洗/重排/生成；交付物必须是电子表文件或可落库表实例。（EN）Use when spreadsheet is the primary artifact."
license: Internal-only (Orient-G). For intranet use only.
---

# 输出要求（Orient-G）

## 安全与合规（硬约束）
- 仅内网：不得把业务数据发送到公网第三方服务
- 禁止在提示词/日志中包含行级原文、合同全文、用户输入全文；只允许使用脱敏摘要与引用（citations）
- 工具调用必须受 allow-list 限制；未允许的 tool 一律拒绝
- 关键路径应产生审计事件：attempt / deny / tool.call / skill.run / generate

## 交付物要求
- 交付物必须明确：是“生成/修改后的电子表文件”，或“已落库的表实例（table_id + citations）”
- 公式/计算应可回归：若产物依赖计算，需给出可重算路径或在服务端校验（避免静默错误）

# 何时使用（When to apply）
- 用户提到 `.xlsx/.xlsm/.csv/.tsv` 文件（文件名/路径/下载目录都算）
- 用户希望做：清洗、对齐表头、重排、透视/汇总、指标口径统一、生成模板化看板数据

# 操作指引（Instructions）
1. 先确认目标交付物：文件、表实例、还是“仅总结不落地”
2. 对输入数据做结构化校验：表头、日期列、币种/单位、缺失值、重复行
3. 若需要指标口径：优先读取“指标/维度字典”（DB），禁止临场发明口径
4. 生成输出：保持可追溯（返回 citations），并做最小一致性校验
5. 若调用工具：必须记录 tool-call（脱敏摘要 + hash），失败不阻断主流程但需返回可读错误
```

这份中文示例在“实际运行中能否生效”的前提是：你们的 Skill 加载器/注册表能读取 `SKILL.md` 的 frontmatter，并将其映射到系统的 `skill.*` 稳定 ID（见本文件第 3 节）。

