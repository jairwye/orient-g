# 财务智能体验收矩阵（页面实测）

> **浏览器实测细则**（Chrome DevTools MCP、CDP runner、hook、timeout）以 **[specs/plans/1.2.3.b-finance-matrix-browser-testing.md](../specs/plans/1.2.3.b-finance-matrix-browser-testing.md)** 为准；本文档为矩阵清单与 API Live 入口。

## 账号与环境

| 项 | 值 |
| --- | --- |
| 账号 | `finance_test` / `FinanceTest!2026` |
| 知识库文件夹 | **竞品财报25**（须勾选） |
| 前端 | http://localhost:3000 |
| 后端 | http://localhost:8000 |
| Hermes | 8642（标准/深度需已连接） |

## 页面实测规范（Chrome DevTools MCP，勿用 Playwright）

### 三条硬性原则

1. **调用 Chrome DevTools 进行页面实测**：使用 **Chrome DevTools MCP**（`user-chrome-devtools`）驱动浏览器完成登录、发问、采样与控制台检查；**禁止** Playwright、Puppeteer 或多 tab 并行抢同一页面。
2. **须确认 LLM 输出完毕后再测下一条**：一次只跑 **1 条**用例；必须等当前问句的 **流式输出完全结束**（见下方判定）并 extract / append 成功后，方可发送下一条问句或进入下一 subject。
3. **Timeout 可设较长，但必须有上限**：单条等待可以设得相对长（标准/深度最长 **1200s**），以便 Hermes 慢响应时轮询仍能撑住；**禁止无限等待**，超时须记录失败并进入「修代码 → 重跑同条」或下一循环，确保 **42 条闭环可持续推进**。
4. **每次实测后审核终稿质量**：流式结束并 extract 后，须人工/Agent **审核最终输出是否符合预期**（见下方「通过标准」与 `finance_matrix_browser_validate.py`）；**不符合则禁止直接 next**——须调研根因（Tier 路由、Hermes 回退、过程稿泄漏、金额/表结构等）→ 调整代码或配置 → **重测同一条**直至 `ok: true` 或明确记录阻塞项。

### 执行细则

- **串行**：严禁「上一条还在流式、下一条已发送」。
- **质量审核**（append 前/后必做）：
  - 看 `tier_line` 是否与所选档位一致；有无 `Hermes 失败后回退`、英文 Evidence Pack 导语、过程稿进主气泡；
  - 看正文：结论 + 表格/结构、金额与 KB 口径、无反推/ unsupported 估算；
  - 看 `append` 返回的 `ok` 与 `checks`；`ok: false` 时 **不得** 当作通过进入下一条。
- **流式完毕判定**（全部满足才采样）：
  - 最后一条 assistant 气泡出现 `citations（N）`（N>0），或诚实「缺少证据」且正文达标；
  - 无「加载中…」「思考中…」「连接流式通道…」；
  - 正文长度连续 2 轮 poll 不变（可选辅证）。
- **Timeout**：脚本/轮询**必须设上限**，可设得较长，以确保后续循环仍可持续推进（不可无限等待）：

| 档位 | 单条最大等待 | 轮询间隔 | 用例间冷却 |
|------|-------------|----------|------------|
| 快速 | **360s** | 15s | 5s |
| 标准 / 深度 | **1200s**（20min） | 15–60s | 5s |

> MCP `evaluate_script` 不可内嵌长循环（协议 timeout）；由 **Agent 侧** sleep + 多次 `poll_state.js` 实现等待。

- **路由确认**：后端日志须出现 `POST /api/agent/chat/stream`（非 `/api/ai-interaction/chat`）；KB 胶囊为 `folder_ids:['f_6f3638…']`。
- **操作顺序**：`navigate`（`folder_id` + `view=agent`）→ 等「智能体模式」→ **nav「智能体」** 新会话 → 选档位 → 发送 → poll → extract → append。

Runner 细则：[`specs/plans/1.2.3.b-finance-matrix-browser-testing.md`](../specs/plans/1.2.3.b-finance-matrix-browser-testing.md)  
报告：`backend/tests/reports/finance_matrix_browser_report.json`  
队列：`python backend/scripts/finance_matrix_browser_retry_queue.py next`

由 Agent 通过 **user-chrome-devtools** 执行（登录与环境）：

1. `navigate_page` → `http://localhost:3000/login`
2. `fill` → `finance_test` / `FinanceTest!2026` → 点击登录
3. `navigate_page` → `/ai-interaction?folder_id=f_6f3638e4513f492c9610ddb5dda77c20&view=agent`
4. initScript 写入 KB 胶囊（`folder_ids` 数组，见 runner）
5. 点 **nav「智能体」** → 选 快速/标准/深度 → 输入问句 → 发送
6. Agent 侧轮询直至流式完毕（见上表 timeout）
7. **审核终稿质量**（Tier、正文、console）；不符则查因 → 改代码 → 重测同条
8. `list_console_messages` types=`["error"]` 检查 depth 循环

## 自动化 TDD

**API Live 矩阵（2026-06-02）**：快档 14/14 · 标准档 14/14 · 深度档 14/14 — 共 **42/42**（`test_agent_finance_live_matrix.py`，串行等 SSE done）

```bash
cd backend
pytest tests/test_agent_finance_acceptance_matrix.py -q
pytest tests/test_hermes_stream_sanitize.py::test_normalize_rd_glued_conclusion_pipe_table_and_shuoming -q
```

Live MCP（本机全栈 + 耐心等待每条流式结束）：

```powershell
$env:ORIENTG_LIVE_FINANCE_MCP="1"
pytest tests/test_agent_finance_acceptance_matrix.py::test_live_finance_mcp_smoke -v --timeout=900
```

## 页面实测清单（每条须等「完成」行出现）

侧栏选 **智能体**，勾选 **竞品财报25**，分别跑 **快速 / 标准 / 深度**。

### 利润表

1. 研发费用 25/24 明细对比分析报告  
2. 销售费用 25/24 明细对比分析报告  
3. 管理费用 25/24 明细对比分析报告  
4. 营业收入 2025 vs 2024 对比  
5. 净利润 2025 vs 2024 对比  

### 资产负债表

6. 货币资金 年末对比  
7. 应收账款 年末对比  
8. 存货 年末对比  
9. 固定资产 账面价值对比  

### 现金流量

10. 经营活动现金流量净额对比  
11. 投资活动现金流量对比  
12. 筹资活动现金流量对比  

### 附注

13. 三项期间费用附注合计对比  
14. 研发支出附注构成变化  

## 通过标准

- 完成行 Tier 与所选档位一致（快速≈Tier0，标准≈Tier1，深度≈Tier2）  
- 正文含 **结论 + 表格**（非 TSV 挤一行）  
- 无 `122568-51705` 类反推分项  
- 浏览器控制台无 `Maximum update depth exceeded`  
- 标准/深度有 MCP 过程时，过程稿为费用/科目相关片段而非无关「市场份额」  

## 回归：研发费用标准轮（用户样例）

问句：`出一份华清25、24两年研发费用明细的对比分析报告`

期望：

- 完成行 **Tier 1（Hermes lite）**
- 终稿含 **结论 + 分项对比表**，且 **不得** 出现「证据中未提供可核查的分项金额」与表并存
- 正文 **不得** 含「约3570万元」类估算（表内精确金额除外）
- 浏览器控制台 **无** `Maximum update depth exceeded`
- 过程稿在「执行过程」中，主气泡为补检索修订后的终稿
