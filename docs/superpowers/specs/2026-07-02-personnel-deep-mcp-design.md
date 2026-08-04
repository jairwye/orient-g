# 人员结构深度档 + Hermes MCP 优化 — 设计说明

## 目标

1. **finance_test + 竞品财报25** 复现与验收（不用 wangjia）。
2. **验收通用化**：从问句提取对比主体 + KB probe 动态锚点，禁止 `1378`/`70.00` 硬编码。
3. **MCP scope**：Hermes Runs 内 `orientg_kb_ask` 在 session kb_scope 缺失时继承 JWT ACL（与网关预检索一致）。
4. **成稿格式**：统一对比表 + 口径说明 + 证据约束分析段（非 excerpt 堆砌）。
5. **深度档**：Hermes 有成稿分析则保留；否则 structured report + 分析，而非 raw dump。
6. **TDD + 浏览器 6 条** personnel 套件复跑通过，且 deep 要求 `hermes_orientg_kb_ask_calls >= 1`（finance_test live）。

## 架构

```
UI kb_scope → persist_session → MCP orientg_kb_ask
                    ↓ (miss)
              token ACL fallback → resolve_kb_scope_for_ask

prefetch citations → build_personnel_compare_excerpts
                   → format_personnel_compare_structured_report (table + 分析)
                   → pick_personnel_compare_final_reply (Tier2 优先 Hermes 分析)
```

## 验收（通用）

| 检查项 | 规则 |
|--------|------|
| 主体 | `extract_query_entity_phrases(query)` 每个实体出现在正文 |
| KB | `probe_kb_evidence_for_query` 金额/人数锚点命中（动态） |
| 误归因 | `personnel_compare_reply_misattributed` |
| 噪声 | 无担保/营业收入大块 dump |
| deep 分析 | 含「对比分析/结构/口径」段，非仅双主体 excerpt 粘贴 |
| deep MCP | done 统计 `hermes_orientg_kb_ask_calls >= 1`（**必填**，采不到即 fail） |
| deep 成稿 | 须含「核心指标对照」；横比 probe **≥2 锚点** |
| deep 策略 | 缺对照表 / 误归因时不保留 Hermes 自由稿，走 structured |

## Hermes 侧（Orient-G 可控范围）

- `hermes_kb_mcp_bridge`：primer 不注入全文；MCP retry instructions 强化 session_key + query。
- `orientg_mcp_tools`：scope 兜底 + 审计日志 `mcp_scope_fallback=token_acl`。
- 政策文档：`docker/hermes/orientg-kb-agent-policy.md` 已约定 Tier2 须 MCP；Runs 第一轮 tool round。

## 非目标

- 修改 Hermes 上游仓库源码（仅 Orient-G 网关 + MCP + 验收）。
- 全站财务矩阵 validate 重写（仅 personnel 套件）。
