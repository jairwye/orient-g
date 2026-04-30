# FP&A Agent：工具调用审计（DB）与口径/指标字典（DB）方案论证（评审稿）

> **目的**：为 v1.2.2 的 AI 互动与数据解析链路补齐两项“可审计 + 口径一致”的工程基础设施：  
> 1) **Tool-call 审计落库**；2) **指标/维度口径字典落库**。  
> **约束**：遵循 [`规则/规则.md`](../规则/规则.md)：仅内网、本地化、最小权限、可审计、日志脱敏；数据库结构变更必须走 Alembic。

---

## 1. 背景与问题

FP&A 场景常见风险：

- **不可追溯**：无法回答“这条结论/数字来自哪次工具调用、用的什么参数、当时版本是什么”。
- **口径漂移**：同一指标在不同对话/不同用户/不同时期口径不一致（模型临场编造或引用混乱）。
- **稳定性压力放大**：网络抖动/重试导致工具调用堆叠，排障困难且成本不可控。

因此需要两类“系统事实源”：

- **审计事实**：发生过什么调用、结果概况、耗时与失败原因（脱敏后）。
- **口径事实**：指标/维度的定义、单位、适用范围、计算约束（可版本化）。

---

## 2. 目标与非目标

### 2.1 目标

- **审计落库**：每次 tool-call 在服务端统一写入 DB。
- **脱敏合规**：不存行级原文/用户隐私/大段 prompt；仅存摘要与 hash。
- **口径统一**：指标/维度字典是唯一权威来源（供解析 pipeline 与 LLM 解读共同引用）。
- **最小权限**：字典维护仅管理员；一般用户只读；审计仅管理员/审计角色可查详情。
- **可回滚**：通过配置开关关闭审计写入与字典强校验（不影响主流程）。

### 2.2 非目标（本轮不做）

- 不做多 Agent 编排平台化。
- 不开放 `run_sql`/`exec_python` 等高副作用工具。
- 不接入公网第三方模型/第三方数据出站。

---

## 3. 总体架构（逻辑）

1) **工具调用统一入口**（现状：`data_parse_chat.py` 的 `execute_tool` / 以及 AI 互动编排层）：  
在“真正执行工具调用”前后插入 `audit_start/audit_finish`，写入 `tool_call_audit_log`。

2) **指标/维度字典服务**：  
新增 `metrics_dictionary`/`dimensions_dictionary`（以及可选的桥接表）作为统一事实源；解析 pipeline 与解读 prompt 都从这里读取（只读）。

---

## 4. 数据库表设计（建议）

以下命名以 PostgreSQL 为目标；字段可按现有工程习惯微调。

### 4.1 Tool-call 审计表：`tool_call_audit_log`

**用途**：记录工具调用“发生过什么”，用于排障、审计、内控与成本评估。

建议字段：

- **id**：UUID（主键）
- **created_at**：timestamptz，默认 now()
- **actor_user_id**：用户 ID（或服务账号）
- **source**：枚举（如：`ai_interaction` / `data_parse_chat` / `kb_pipeline` / `system`）
- **request_id / trace_id**：用于链路关联（如已有 request id 则复用）
- **session_id**：可选（数据解析会话 / AI 互动会话）
- **tool_name**：字符串（与 allow-list 的 tool id 对齐）
- **tool_version**：可选（工具/skill 版本号或实现版本）
- **input_json**：jsonb（**脱敏后的**入参；严格裁剪与白名单）
- **input_hash**：text（对原始入参序列化后做 hash，用于去重/对齐，但不落原文）
- **output_json**：jsonb（**脱敏后的**结果摘要；禁止落长文本与原始明细）
- **ok**：boolean
- **error_code**：可选（如 `TIMEOUT`/`DENY`/`VALIDATION_ERROR`）
- **error_message**：可选（裁剪长度，如 512/1024）
- **latency_ms**：integer

脱敏原则（强制）：

- 禁止写入：上传文件原文内容、表格行级明细、KB chunk 原文、长 prompt、用户输入全文。
- 允许写入：文件/任务/会话的 ID、数量级统计（行数、列数、页数）、字段名列表（裁剪）、异常计数、hash、耗时。

### 4.2 指标字典表：`fpa_metric_def`

**用途**：指标“口径事实源”，用于生成/校验/展示。

建议字段：

- **id**：UUID
- **metric_key**：text（稳定 key，如 `revenue`/`gross_margin_pct`；全局唯一）
- **name_cn**：text
- **description**：text（业务解释）
- **unit**：text（如 `CNY`/`USD`/`pct`/`count`）
- **value_type**：枚举（`number`/`percent`/`currency`/`string`）
- **formula_hint**：text（非可执行，仅说明；避免引入可执行表达式）
- **default_aggregation**：枚举（`sum`/`avg`/`last`/`ratio` 等）
- **dimensions_allowed**：jsonb（允许的维度 key 列表）
- **owner_team**：text（维护责任方）
- **is_active**：boolean
- **version**：integer（从 1 起）
- **effective_from / effective_to**：timestamptz（可选）
- **created_at / updated_at**：timestamptz

### 4.3 维度字典表：`fpa_dimension_def`

建议字段：

- **id**：UUID
- **dimension_key**：text（如 `project`/`region`/`channel`；全局唯一）
- **name_cn**：text
- **description**：text
- **value_type**：枚举（`string`/`date`/`number` 等）
- **cardinality_hint**：枚举（`low`/`medium`/`high`，用于提示 UI/性能策略）
- **is_active**、**version**、**effective_from/to**、**timestamps** 同上

### 4.4 关系（可选）：`fpa_metric_dimension_link`

若不想在 `fpa_metric_def.dimensions_allowed` 放 jsonb，可用桥接表：

- **metric_key** + **dimension_key** 复合唯一
- **is_required**、**notes**

---

## 5. 写入点与最小实现路径

### 5.1 Tool-call 审计写入点

优先覆盖两条链路（最小闭环）：

- **数据解析解读**：`backend/services/data_parse_chat.py` 的工具执行统一入口（如 `execute_tool`）
- **AI 互动**：`backend/services/ai_interaction_llm.py`（或其编排层）中 tool/skill 执行入口

实现要点：

- 审计写入由服务端完成（模型不可控）。
- 输入/输出脱敏必须在写库前完成（白名单字段 + 长度裁剪 + hash）。
- 允许失败不影响主流程：审计写入异常应吞掉并上报到应用日志（不阻断业务）。

### 5.2 指标/维度字典接入点

- 解析 pipeline（指标命名、单位、默认聚合）优先从字典读取；
- LLM 解读 prompt 注入：只注入 **字典摘要**（metric_key + name_cn + unit + 口径说明要点），禁止注入任何行级原始数据。

---

## 6. 接口建议（最小）

### 6.1 字典读取（只读）

- `GET /api/fpa/metrics`：返回指标列表（支持 `?active=1`）
- `GET /api/fpa/dimensions`：返回维度列表

### 6.2 字典维护（管理员）

- `POST /api/fpa/metrics` / `PUT /api/fpa/metrics/{metric_key}`（或版本化新建）
- `POST /api/fpa/dimensions` / `PUT /api/fpa/dimensions/{dimension_key}`

### 6.3 审计查询（管理员/审计角色）

- `GET /api/audit/tool-calls`：按时间/用户/source/tool_name/session_id 查询（分页）
- `GET /api/audit/tool-calls/{id}`：详情（仍需脱敏，避免回显敏感明细）

---

## 7. 配置开关与回滚策略

建议新增配置：

- `ENABLE_TOOL_CALL_AUDIT`：默认开；关掉则不写审计表
- `ENABLE_FPA_DICTIONARY`：默认开；关掉则回退到旧的“无字典约束”模式（仅用于紧急回滚）

回滚原则：

- 字典表可先空跑上线（不强制约束）；填充稳定后逐步开启“强约束/校验”。
- 审计写入失败不影响主链路，天然可回滚（关开关 + 不再写）。

---

## 8. Alembic 迁移策略（概述）

- 新增 3~4 张表（审计表 + 指标表 + 维度表 + 可选桥接表）
- 增加必要索引：
  - `tool_call_audit_log(created_at, tool_name)`
  - `tool_call_audit_log(actor_user_id, created_at)`
  - `fpa_metric_def(metric_key unique)`
  - `fpa_dimension_def(dimension_key unique)`

---

## 9. 验收口径（建议）

- 能在一次 data-parse 解读与一次 ai-interaction 会话中，查询到对应的 tool-call 审计记录（包含 tool_name、ok、latency、input/output 摘要）。
- 指标/维度字典能被读取（只读接口可用），并能在解读 prompt 中以“摘要形式”稳定注入（不含敏感明细）。
- 关闭 `ENABLE_TOOL_CALL_AUDIT` 后主流程不受影响。

