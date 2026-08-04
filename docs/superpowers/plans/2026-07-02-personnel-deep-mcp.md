# 人员深度档 + Hermes MCP — 实施计划

> **status:** superseded（2026-08-04）  
> **现行规制：** [`specs/plans/1.2.3.c-personnel-browser-testing.md`](../../../specs/plans/1.2.3.c-personnel-browser-testing.md)（8 条矩阵）、[`specs/plans/1.2.3.d-hermes-native-mcp-tdd.md`](../../../specs/plans/1.2.3.d-hermes-native-mcp-tdd.md)（`retry=0` / deep `hermes≥2` / 禁骨架·thin salvage）。  
> 下文保留历史任务记录；验收口径以 1.2.3.c / 1.2.3.d 为准（不再要求 6/6 或仅 `hermes_kb_ask_calls >= 1`）。

> **Goal（历史）：** finance_test 人员横比深度档：MCP 可用、成稿有分析、验收无硬编码锚点、浏览器 6/6。

**Architecture:** MCP scope token ACL 兜底 → structured personnel report → 通用 validate（实体+KB probe+分析+MCP 统计）→ personnel CDP 复跑。

---

### Task 1: MCP scope 兜底（已完成代码）

- `backend/services/orientg_mcp_tools.py` — session kb_scope 空时用 JWT `allowed_collection_ids`
- Test: `test_hermes_personnel_mcp_bridge.py` + 新增 `test_mcp_kb_scope_token_acl_fallback`

### Task 2: 结构化成稿

- `backend/services/personnel_compare_report.py`
- `format_personnel_compare_report` 委托 structured
- Test: `test_personnel_compare_report.py`

### Task 3: 通用验收

- `backend/scripts/finance_matrix_personnel_validate.py` — 去 COMPARE_ANCHORS
- `finance_matrix_browser_validate.py` — 传入 kb_probe
- `finance_matrix_browser_poll_state.js` — 解析 `hermes_kb_ask_calls`

### Task 4: Tier2 成稿策略

- `pick_personnel_compare_final_reply` — 优先 Hermes 分析；fallback structured

### Task 5: 浏览器 + Live

```powershell
cd backend
py -3.10 -m pytest tests/test_personnel_compare_report.py tests/test_hermes_personnel_mcp_bridge.py tests/test_agent_kb_supplemental.py -q
$env:ORIENTG_LIVE_PERSONNEL_MCP="1"
py -3.10 -m pytest tests/test_hermes_personnel_live_mcp.py -q
py -3.10 backend/scripts/finance_matrix_personnel_cdp_runner.py --skip-login
py -3.10 backend/scripts/finance_matrix_personnel_retry_queue.py count
```

**Expected:** `ok_pass: 6/6`；deep 行 `personnel_analysis_ok: true`；`hermes_kb_ask_calls >= 1`（若 Trace 可见）。
