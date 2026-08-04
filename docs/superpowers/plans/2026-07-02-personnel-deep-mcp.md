# 人员深度档 + Hermes MCP — 实施计划

> **Goal:** finance_test 人员横比深度档：MCP 可用、成稿有分析、验收无硬编码锚点、浏览器 6/6。

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
