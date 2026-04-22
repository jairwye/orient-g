# Skill 编写通行规范（Orient-G）

本文件用于约束与统一本仓库中 “Skills（技能）” 的设计与实现方式，保证安全、可审计、可回归、可继承。本文档 **进入 Git**，作为团队协作的共同口径。

## 1. Skill 的定位

- **Skill 是业务能力封装**：以稳定的输入/输出 schema 表达一个“可复用动作”，例如：生成项目核算表、生成合同台账草稿、生成流程文档等。
- **Tool 是基础能力**：例如 Docling 转换、MCP 只读查询、渲染等。
- Skill 可以调用 Tool，但 **Skill 必须对业务结果负责**（验证、落库、产出引用）。

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

- **每个 Skill 必须有稳定 ID**：推荐 `skill.<domain>.<name>.v<major>`，例如 `skill.project_accounting_table.v1`。
- **输入必须结构化**：即使用户以自然语言触发，也应在 Skill 内部转换为结构化输入并校验。
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

