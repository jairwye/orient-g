# Hermes × Orient-G 联调指南

> **规制与实施计划**（产品方案，非操作手册）：  
> [`specs/features/1.2.3-Hermes-Agent与Orient-G融合方案.md`](../specs/features/1.2.3-Hermes-Agent与Orient-G融合方案.md)  
> [`specs/plans/1.2.3-hermes-integration-plan.md`](../specs/plans/1.2.3-hermes-integration-plan.md)

---

## 0. 只有一套目标架构（开发与上线一致）

开发环境的目的，是跑通**与生产相同的产品链路**，不是维护「开发专用方案」。  
允许的差异只有：**部署形态**（本机进程 vs Docker）、**连接地址**（`127.0.0.1` vs `hermes-agent`）、**数据库**（开发库 vs 生产库）。

**上线形态（开发机应对齐这一条）：**

```text
浏览器登录 → JWT 在请求头
    → Orient-G backend（/api/agent/chat，鉴权用户）
        → POST {HERMES_BASE_URL}/v1/chat/completions
            （服务密钥 HERMES_INTERNAL_TOKEN，非用户 JWT）
            → Hermes Gateway（编排 + LLM）
                → MCP orientg（stdio）
                    → MCP 参数 hermes_session_key → bridge 解析当前用户 JWT（非运维每人一条 env）
                        → orientg_server → PostgreSQL（本环境 DATABASE_URL）
```

| 组件 | 开发 / 生产是否同一套逻辑 |
|------|---------------------------|
| 用户登录、JWT、`/api/agent/chat` | **是** |
| `HERMES_ENABLED` + `HERMES_DEV_MOCK=false` | **是**（mock 仅见 §6，不算第二套系统） |
| Hermes Gateway + `API_SERVER_KEY` | **是**（host/port 不同） |
| MCP `orientg_kb_*` + ACL | **是** |
| 多用户各用各的 JWT | **是**（见 §4；勿在生产 config 写死单一用户 token） |

**不应作为「开发第二方案」长期依赖的：**

- `HERMES_DEV_MOCK=true`（绕过 Hermes，只验 Python 函数）
- 仅在 `hermes chat` 自测时、临时把**你自己的** JWT 写进 `~/.hermes/.env`（等价于单人调试，≠ 多用户生产）
- 「本机 backend + 远程生产 Hermes」且 MCP 仍在生产容器（测不到本机 MCP 代码）

---

## 我该看哪一节？

| 场景 | 章节 |
|------|------|
| **开发机落地（与上线同链路，本机库）** | [§2](#2-开发机落地) |
| **生产机落地（Docker，生产库）** | [§3](#3-生产机落地) |
| **多用户 JWT（为何不用每人配 env）** | [§4](#4-多用户与-jwt) |
| **Hermes 流式 / 工具进度 SSE** | [§5](#5-流式-sse页面还原-hermes-工具进度) |
| **pytest / mock（单元冒烟，非产品链路）** | [§6](#6-单元冒烟非产品链路) |

---

## 1. 开发与生产：仅部署差异

| 项 | 开发机 | 生产机 |
|----|--------|--------|
| Orient-G backend | 本机 `uvicorn` | `backend` 容器 |
| Hermes | 本机 CLI + `hermes gateway`（或日后同 compose） | `hermes-agent` 容器 |
| `HERMES_BASE_URL` | `http://127.0.0.1:8642` | `http://hermes-agent:8642` |
| MCP 启动 | 本机 `python -m backend.mcp.orientg_server` | `docker exec` 进 backend 容器 |
| `DATABASE_URL` | 本机 PostgreSQL | 生产 PostgreSQL |
| `.env.hermes` / Gateway | `%USERPROFILE%\.hermes\.env` | 项目根 `.env.hermes` + 卷 |

- **不**把 `8642` 暴露公网；生产仅 compose 内网。
- KB 读写**必须**走 MCP。

---

## 2. 开发机落地

### 2.1 配置文件放在哪

| 作用 | 路径 |
|------|------|
| Hermes LLM / MCP / Gateway | `%USERPROFILE%\.hermes\config.yaml` |
| Hermes Gateway 密钥 | [`docker/hermes/dotenv.hermes.gateway.example`](../docker/hermes/dotenv.hermes.gateway.example) → `%USERPROFILE%\.hermes\.env` |
| Orient-G 数据库、业务配置 | 项目根 **`.env`**（`DATABASE_URL` 等，见 [`.env.example`](../.env.example) 本地开发段） |
| MCP 配置示例（可复制） | [`docker/hermes/mcp-orientg.windows.example.yaml`](../docker/hermes/mcp-orientg.windows.example.yaml) |
| 单人 CLI JWT（可选） | [`docker/hermes/dotenv.hermes.orientg.example`](../docker/hermes/dotenv.hermes.orientg.example) |
| 生产 Hermes 容器 env | [`docker/hermes/env.hermes.example`](../docker/hermes/env.hermes.example) → 项目根 `.env.hermes` |

### 2.2 安装 Hermes CLI（Windows）

PowerShell（无需管理员）：

```powershell
iex (irm https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.ps1)
```

装好后**新开终端**：`hermes --version`、`hermes doctor`。  
若 `uv` 安装 Python 报「拒绝访问」，可用 winget 安装 Python 3.11 后在仓库目录用 `py -3.11 -m venv` 完成依赖安装（见官方 [Windows Native](https://hermes-agent.nousresearch.com/docs/user-guide/windows-native)）。

### 2.3 MCP：`config.yaml`

在 `%USERPROFILE%\.hermes\config.yaml` 顶层增加 `mcp_servers`（路径改成你的项目根与 `.venv`）：

```yaml
mcp_servers:
  orientg:
    command: "E:/jair/SynologyDrive/游艺春秋/Projects/orient-g/.venv/Scripts/python.exe"
    args:
      - "-m"
      - "backend.mcp.orientg_server"
    cwd: "E:/jair/SynologyDrive/游艺春秋/Projects/orient-g"
    env:
      PYTHONPATH: "E:/jair/SynologyDrive/游艺春秋/Projects/orient-g"
      ORIENTG_USER_TOKEN: "${ORIENTG_USER_TOKEN}"
    timeout: 180
    connect_timeout: 60
```

- Hermes 注册的工具名形如：`mcp_orientg_orientg_kb_ask`。
- **`cwd` 为项目根**时，`backend/config.py` 会读该项目 **`.env`** 里的 `DATABASE_URL`，无需在 Hermes 里再写数据库连接。

### 2.4 `%USERPROFILE%\.hermes\.env`

从 [`docker/hermes/dotenv.hermes.gateway.example`](../docker/hermes/dotenv.hermes.gateway.example) 复制到 `%USERPROFILE%\.hermes\.env` 后改 `API_SERVER_KEY`。

**走浏览器 `/agent` 完整链路时，这里不必写用户 JWT。** 用户登录后 JWT 随 `/api/agent/chat` 进入 backend，经 `hermes_token_bridge` + `hermes_session_key` 交给 MCP（见 [§4](#4-多用户与-jwt)）。本节**必须**配置的是 Gateway 服务密钥（与项目根 `.env` 的 `HERMES_INTERNAL_TOKEN` 一致）。

```env
# Gateway（/agent 完整链路必需）
API_SERVER_ENABLED=true
API_SERVER_HOST=127.0.0.1
API_SERVER_PORT=8642
API_SERVER_KEY=请设一长随机串
```

`config.yaml` 里 MCP 的 `ORIENTG_USER_TOKEN: "${ORIENTG_USER_TOKEN}"` 可保留占位；**不填 `.env` 时**，`/agent` 路径仍可通过 `hermes_session_key` 解析 JWT。

**仅**在本机 `hermes chat` 直接点 MCP、且**不经过** Orient-G backend 时，才临时加一行（你自己的登录 JWT，单人调试）：

```env
ORIENTG_USER_TOKEN=eyJ...
```

LLM 若在 `config.yaml` 的 `model:` 段已配好，可不再重复写 `OPENAI_API_BASE`。

启动 Gateway：

```powershell
hermes gateway start
curl http://127.0.0.1:8642/health
```

### 2.5 项目根 `.env`（Orient-G backend，与生产同形）

从 [`.env.example`](../.env.example) 复制为 `.env`，至少配置本机库与 Hermes 段（完整模板见示例文件）：

```env
# 本机 PostgreSQL（与生产库隔离；Windows 建议 127.0.0.1）
DATABASE_URL=postgresql://postgres:你的密码@127.0.0.1:5432/mgmt_web

HERMES_ENABLED=true
HERMES_DEV_MOCK=false
HERMES_BASE_URL=http://127.0.0.1:8642
HERMES_INTERNAL_TOKEN=<与 .hermes\.env 中 API_SERVER_KEY 相同>
HERMES_MODEL=hermes-agent
HERMES_REQUEST_TIMEOUT_S=300
```

重启本机 `uvicorn`，检查 `GET /api/agent/status` → `hermes_configured: true`，`hermes_dev_mock_active: false`。

**Agent 页（Evidence Pack + Tier 0–2，见 [1.2.3.b 规制](../specs/features/1.2.3.b-agent-evidence-pack-tiers.md)）：**

| Tier | `agent_route` | 行为 |
|------|---------------|------|
| 0 | `fast` | 多 query 预检索 → **Evidence Pack** → Orient-G 本地 LLM 综合（`hermes_used=false`） |
| 1 | `hermes_lite` | 注入 pack；Hermes 编排；`orientg_kb_ask` 补检索预算默认 ≤2；**勿用 terminal 编造证据** |
| 2 | `hermes_full` | 深度 / 写库 / 无 KB；完整工具环 |

`HERMES_AGENT_KB_PREFETCH=true` + `HERMES_AGENT_KB_MULTI_QUERY=true`（默认）时网关执行检索计划（1–4 子 query）并合并 citation。`HERMES_AGENT_STANDARD_TIER0=true`（默认）时 **仅 auto 模式**在 pack 覆盖率足够且无需多轮编排时走 Tier 0；**标准模式固定 Tier 1 Hermes lite**。前端三档：`agent_mode=fast|standard|deep`。SSE `done` 含 `agent_tier`、`evidence_pack` 摘要。`GET /api/agent/status` 含 `hermes_agent_kb_multi_query`、`hermes_agent_standard_tier0`。

**MCP 硬约束：** `hermes_client` 按 `HERMES_AGENT_KB_ASK_BUDGET_LITE` 为每个 `hermes_session_key` 登记预算；超额时 `orientg_kb_ask` 返回 `denied`（网关预检索不计入该预算）。**AI 互动**对话 RAG 与 Agent 同源（`retrieve_kb_for_chat`），响应含 `evidence_pack`。

前端 `npm run dev` 时，确保 API 指向本机 backend（如 `frontend/.env.local` 中的 `API_URL` / `NEXT_PUBLIC_API_URL`）。

**仅当你暂时不用 `/agent`、只在本机 `hermes chat` 里点 MCP 时**，才可在 `~/.hermes\.env` 临时写**你自己的** `ORIENTG_USER_TOKEN` 做单人调试；这与浏览器多用户链路不同，不能代替 §4 的验收。

### 2.6 验证（开发）

```powershell
# 1) Hermes + MCP（CLI）
hermes chat
# 例如：用 orientg 知识库检索财务制度

# 2) Orient-G MCP 冒烟（可不启 Hermes）
cd E:\jair\SynologyDrive\游艺春秋\Projects\orient-g
.\.venv\Scripts\python.exe scripts\smoke_orientg_mcp.py --ensure-user

# 3) /agent（需 2.4 Gateway + 2.5；浏览器登录即可，勿在 .hermes\.env 写死 JWT）
# 浏览器：AI 互动 → Agent
```

---

## 3. 生产机落地

### 3.1 配置文件

| 作用 | 路径 |
|------|------|
| Compose overlay | [`docker-compose.hermes.yml`](../docker-compose.hermes.yml) |
| Hermes 容器环境 | 项目根 **`.env.hermes`**（从 [`docker/hermes/env.hermes.example`](../docker/hermes/env.hermes.example) 复制） |
| Orient-G backend | 项目根 **`.env`**（生产机一份，与开发机分开） |
| MCP 片段（docker exec） | [`docker/hermes/mcp-orientg.snippet.json`](../docker/hermes/mcp-orientg.snippet.json) |

### 3.2 `.env.hermes`（Hermes 容器）

```env
API_SERVER_ENABLED=true
API_SERVER_HOST=0.0.0.0
API_SERVER_PORT=8642
API_SERVER_KEY=长随机串

OPENAI_API_BASE=http://host.docker.internal:8080/v1
OPENAI_API_KEY=
```

`OPENAI_API_BASE` 指向与 Orient-G `LLM_BASE_URL` 相同的内网 llama.cpp（或网关地址）。

### 3.3 生产 `.env`（Orient-G backend）

```env
HERMES_ENABLED=true
HERMES_DEV_MOCK=false
HERMES_BASE_URL=http://hermes-agent:8642
HERMES_INTERNAL_TOKEN=<与 .env.hermes 中 API_SERVER_KEY 相同>
HERMES_MODEL=hermes-agent
```

`DATABASE_URL` 指向**生产 PostgreSQL**（与开发机 `.env` 不同文件、不同库）。

### 3.4 启动

```bash
cp docker/hermes/env.hermes.example .env.hermes
# 编辑 .env.hermes、.env 后：

docker compose -f docker-compose.yml -f docker-compose.hermes.yml up -d
```

### 3.5 MCP（生产）

1. `docker ps` 查 backend 容器名，替换 [`mcp-orientg.snippet.json`](../docker/hermes/mcp-orientg.snippet.json) 中的 `BACKEND_CONTAINER_NAME`。
2. 将 `mcp_servers` 合并进 Hermes 状态卷（`hermes_state` → 容器内 `/root/.hermes/config.yaml`）。

等价命令：

```bash
docker exec -i -e ORIENTG_USER_TOKEN=<用户JWT> <backend容器> python -m backend.mcp.orientg_server
```

MCP 配置里**不要**写死某一用户的 JWT；多用户见 [§4](#4-多用户与-jwt)。

### 3.6 健康检查

```bash
curl -s http://hermes-agent:8642/health
curl -s -H "Authorization: Bearer <API_SERVER_KEY>" http://hermes-agent:8642/v1/models
curl -s http://backend:8000/api/agent/status
```

浏览器登录 → **AI 互动 → Agent** → 发送知识库检索类任务。

### 3.7 改 MCP 代码后（不必每次打镜像）

在生产/预发机（Linux + Docker）：

```bash
git pull
docker compose -f docker-compose.yml -f docker-compose.hermes.yml -f docker-compose.dev-server.yml up -d backend
```

[`docker-compose.dev-server.yml`](../docker-compose.dev-server.yml) 挂载 `./backend` 并 `--reload`。  
仅改 Hermes 配置时：`docker compose restart hermes-agent backend`。

**封版**（依赖变更、多机发布）再 `docker build` / `push` GHCR 镜像。

---

## 4. 多用户与 JWT

**生产不为每个用户配置环境变量。** 运维只配服务级密钥；用户 JWT 由浏览器登录产生，随每次 `/api/agent/chat` 带到 Orient-G backend。

| 凭证 | 谁持有 | 用途 |
|------|--------|------|
| 用户 JWT | 各用户浏览器 → backend | 识别「当前是哪个用户」 |
| `HERMES_INTERNAL_TOKEN` / `API_SERVER_KEY` | 运维，全员共用 | backend ↔ Hermes 内网调用 |
| `ORIENTG_USER_TOKEN`（MCP 子进程） | 勿在生产写死；多用户靠 **`hermes_session_key` 工具参数**（见下） | MCP 按该用户 ACL 访问 KB |

目标数据流：

```text
用户 A 登录 → /api/agent/chat 带 A 的 JWT
    → backend 登记 hermes_token_bridge[orientg-<session>] = A 的 JWT
    → backend 调 Hermes（HERMES_INTERNAL_TOKEN + X-Hermes-Session-Key）
    → Hermes 调 orientg_kb_* 时传入 hermes_session_key（见 system 指令）
    → MCP resolve_user_token(hermes_session_key) → A 的 JWT → KB ACL
```

**已实现（backend，TDD 覆盖）：**

| 组件 | 作用 |
|------|------|
| `backend/services/hermes_token_bridge.py` | 内存 TTL：`session_key` → `user_token`（默认 3600s） |
| `backend/services/hermes_client.py` | 每次 `run_agent_chat` 前 `register`；请求头 `X-Hermes-Session-Key`；system JSON 含 `orientg_hermes_session_key`、`orientg_mcp_instruction` |
| `backend/services/orientg_mcp_tools.py` / `backend/mcp/orientg_server.py` | 各 `orientg_kb_*` 可选参数 `hermes_session_key`；`resolve_user_token()` 优先 bridge，否则 `ORIENTG_USER_TOKEN` 环境变量（单人 CLI） |

**Hermes 上游 MCP 环境变量（已核对 [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) `tools/mcp_tool.py`，发布 `v2026.5.29` / 包 `0.15.1`）：**

- stdio 子进程仅在 **连接 MCP 时** 得到 `config.env` + 安全基线（PATH/HOME 等）；`${VAR}` 在 **server-connect 时** 从 `os.environ`（含 `~/.hermes/.env`）解析一次。
- **没有**「每次 tool call 前按 Orient-G 会话动态改写子进程环境」的 API。
- 因此 **不能** 指望配置里写 `ORIENTG_USER_TOKEN: "${ORIENTG_USER_TOKEN}"` 就实现生产多用户 JWT 自动注入；compose 默认镜像 **`nousresearch/hermes-agent:latest`**（可用 `HERMES_IMAGE` 覆盖为具体 tag）。

**Orient-G 当前多用户做法（开发与生产统一）：** backend `hermes_token_bridge` + system 要求 LLM 在 MCP 工具参数中带 `hermes_session_key`（与 `X-Hermes-Session-Key` 一致）。若模型漏传 → ACL 失败或误用 env 兜底（生产会打 warning）。

**写库 / 写技能（与 JWT 机制无关，见下节 FAQ）：** MCP 已注册 `orientg_kb_upload` / `assign` / `import_artifact`；**无** `orientg_skill_submit` 类工具——技能固化不走 Hermes MCP。

**单人 CLI 调试：** 在 `~/.hermes/.env` 或 MCP 启动环境设置 `ORIENTG_USER_TOKEN=<JWT>`，可不传 `hermes_session_key`。

---

## 5. 流式 SSE（页面还原 Hermes 工具进度）

Orient-G Agent 经 `backend/services/hermes_client.py` 调用 Hermes Gateway `POST /v1/chat/completions`（`stream: true`）。除标准 OpenAI `data:` 正文 delta 外，Hermes 会发**自定义 SSE**（见 [API Server 文档](https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server)）：

| Hermes SSE | Orient-G → 浏览器 SSE | 前端展示 |
|------------|------------------------|----------|
| `data:` + `choices[].delta.content` | `type: delta` | 助手正文流式 |
| `data:` + `reasoning_content`（若模型支持） | `type: thinking` | 执行过程 · 思考片段 |
| `event: hermes.tool.progress` + JSON | `type: tool_progress` | 执行过程 · 工具（emoji + label，按 `tool_call_id` running→completed） |
| OpenAI `delta.tool_calls`（回退） | `type: tool_call` | 执行过程 · 工具名 |

请求体显式设置 `stream_tool_progress: true`（Hermes 默认亦为 true），避免仅收到最终答案而无工具生命周期。

**验收：** 标准/深度模式下提问触发 MCP 时，助手气泡「执行过程」应出现带 emoji 的工具行，完成后显示「（完成）」；正文不应混入 `🔧 terminal: …` 类工具进度字符串（Hermes 已用独立 event 隔离）。

**单测：** `backend/tests/test_hermes_stream.py`（`HermesSseParser`）；前端 `agentTraceUtils.test.ts`（`upsertAgentToolTrace`）。

**深度模式（Tier 2 / `hermes_full`）默认 Runs API：** 当 Gateway `GET /v1/capabilities` 报告 `run_events_sse` + `run_submission` + `run_stop` 时，Orient-G **无需**再设 `HERMES_AGENT_USE_RUNS_API=true`，`stream_agent_chat` 会自动走 `POST /v1/runs` + 事件流（多轮 MCP 工具事件更易透传）。若 capabilities 不满足，会回退 `chat/completions` 并在执行过程提示「工具步可能不可见」。

**编排观测（`done.hermes_stream_stats`）：** 流式结束时浏览器 `done` 含 `hermes_stream_mode`（`runs` | `chat_completions`）与统计：`thinking_chars`、`delta_chars`、`tool_progress_events`、`orientg_kb_ask_calls`。AI 互动页「执行过程」完成行会附带「编排观测：…」；**Tier 2 且 `orientg_kb_ask_calls=0`** 时提示「可能单轮 completion 或未开 Runs API」，便于区分 **reasoning budget 截断**（推理流有字、无工具）与 **多轮 MCP 未触发**（无工具事件）。

**仍可用 env 强制：** `HERMES_AGENT_USE_RUNS_API=true` 时，标准/深度在 capabilities 满足时均走 Runs；`POST /api/agent/cancel` 会联动 `POST /v1/runs/{id}/stop`。`done` 事件含 `hermes_stream_mode: runs`。

**路线第四步：** `GET /v1/capabilities` 由 backend 缓存 120s，并在 `GET /api/agent/status` 返回 `hermes_capabilities`、`hermes_runs_api_ready`。

**单测：** `test_hermes_capabilities.py`、`test_hermes_runs_stream.py`、`test_agent_run_hermes_bind.py`、`test_agent_cancel_hermes_stop.py`、`test_stream_agent_chat_routes.py`、`test_diagnose_hermes_capabilities.py`、`test_hermes_tool_progress_labels.py`；前端 `agentSseTrace.test.ts`、`agentTraceUtils.test.ts`。

**执行过程里的 `terminal`：** 表示 Hermes 在**本机/容器沙箱**里执行了 shell 命令（如 `cat`、`grep` 某路径）。Orient-G **不会**把终端 stdout 全文写入知识库或气泡；仅透传 Gateway 的 **命令预览**（`hermes.tool.progress` 的 `label`）。若完成态只显示「terminal（完成）」而无命令，属 completed 事件未带 label——已由 `enrich_tool_progress_with_labels` / 前端 `mergeToolProgressMessage` 修复。终端输出**不会**自动入库，除非 Hermes 再调 `orientg_kb_import_artifact` 等写库工具。

**Tier 1/2 禁 terminal（产品约定）：** Gateway 在 `orientg_route=hermes_lite|hermes_full` 时于 system JSON 注入 `orientg_forbidden_tools: ["terminal", "skill_view", "orientg-debugging"]` 与 `orientg_tool_policy`（仅 `orientg_kb_*` 取证，禁止 curl/openapi 探测）。Hermes 仍可能通过 Gateway 执行 terminal——若 Trace 出现 `curl`/`import urllib`，属 Hermes 侧未拦截；Orient-G 网关会将此类文本**分流到「推理过程」**，不写入主气泡正文。

**推理 vs 正文（Orient-G 网关）：** 若模型把计划/脚本写在 `content` 而非 `reasoning_content`，`hermes_stream_sanitize` 会将其映射为 SSE `thinking`；用户可见报告（`###`、表格等）才进入 `delta`/`done.reply`。补检索在 Hermes `done` **之后**执行，可能 `replace_reply`；若本地重综合更差则保留 Hermes 原文（Trace：`保留 Hermes 原文`）。

**智能体 ↔ Hermes 会话：** 请求体传 `orientg_chat_session_id`（侧栏会话 `s_…`）+ 可选 `hermes_session_id`（首轮 done 后持久化）。backend 解析为 `orientg-{username}--{chat_id}`，**同用户续聊同会话、换用户隔离、新建智能体对话=new chat id**。

**v1 已知限制（多实例）：** `hermes_token_bridge` 与 `kb_ask_budget` 为进程内内存；`uvicorn --workers N` 或多副本部署时 MCP 会话 JWT / Tier 1 补检索预算不跨 worker 共享。单机单 worker 为当前推荐；多实例需后续 Redis 会话桥（见 code review I2）。

---

## 6. 单元冒烟（非产品链路）

与 §0 主链路**并行**，用于改代码时快速反馈；**不能**替代 §2 / §3 验收。

| 方式 | 说明 |
|------|------|
| pytest | `cd backend && pytest tests/test_hermes_token_bridge.py tests/test_hermes_client_token.py tests/test_orientg_mcp_session_key.py tests/test_hermes_client.py tests/test_hermes_stream.py tests/test_agent_router.py tests/test_agent_finance_e2e.py tests/test_orientg_mcp_*.py -q` |
| Agent 财务冒烟 | `python scripts/smoke_agent_finance.py --ensure-user --kb`；`--cost-detail`、`--huaqing`、`--chat-rag` 见 [1.2.3.b 实测清单](../specs/plans/1.2.3.b-acceptance-tests.md) |
| 一键验收 | `.\scripts\run_acceptance_evidence_pack.ps1`（pytest + jest + 冒烟） |
| `smoke_orientg_mcp.py` | 进程内调 MCP 工具 |
| `HERMES_DEV_MOCK=true` | `/agent` 绕过 Hermes（默认应 `false`） |

---

## 7. 环境变量对照

| 变量 | 开发 `.env` | 生产 `.env` | `~/.hermes/.env` | `.env.hermes` |
|------|-------------|-------------|------------------|---------------|
| `DATABASE_URL` | 本机库 | 生产库 | — | — |
| `HERMES_ENABLED` | **`true`**（与生产一致） | `true` | — | — |
| `HERMES_DEV_MOCK` | **`false`** | **`false`** | — | — |
| `HERMES_BASE_URL` | `http://127.0.0.1:8642` | `http://hermes-agent:8642` | — | — |
| `HERMES_INTERNAL_TOKEN` | = `API_SERVER_KEY` | 同左 | — | — |
| `API_SERVER_*` | — | — | 本机 Gateway | 容器 Gateway |
| `ORIENTG_USER_TOKEN` | 仅单人 CLI 调试临时用 | — | 勿写死 | 勿写死 |

---

## 8. 验收清单

完成 **≥2 项**后再对业务开放 `/agent`。**开发与生产各跑一遍同一清单**（仅库与 URL 不同）。

| # | 任务 | 开发 | 生产 |
|---|------|:----:|:----:|
| 1 | Hermes 连内网 LLM，完成一轮对话 | ☐ | ☐ |
| 2 | MCP `orientg_kb_ask` 检索并带 doc_id 引用 | ☐ | ☐ |
| 3 | MCP `orientg_kb_import_artifact` 写入私人库（写 ACL） | ☐ | ☐ |
| 4 | `/agent` 续聊：`orientg_chat_session_id` 或 `hermes_session_id` 稳定绑定 | ☐ | ☐ |
| 推理/脚本出现在主气泡？ | 升级 backend 后应只在「推理过程」；检查 `test_hermes_stream_sanitize.py` |
| 答案先出后又变？ | Hermes 流式结束后 Orient-G **补检索**可能 `replace_reply`；更差时保留 Hermes（见上） |

---

## 9. 常见问题

| 现象 | 处理 |
|------|------|
| `/agent` 503 `hermes_disabled` | 对应环境 `.env` 未设 `HERMES_ENABLED=true` 或未重启 backend |
| 502 无法连接 Hermes | Gateway 未起；开发 `127.0.0.1:8642`，生产 `hermes-agent:8642` |
| 502 HTTP 401 | `HERMES_INTERNAL_TOKEN` ≠ `API_SERVER_KEY` |
| MCP 无 orientg 工具 | 检查 `mcp_servers`、Python 路径、`cwd`、容器名（生产） |
| KB deny | 用 `finance_test` 或确认对 `c_finance_public_1` 有读权限 |
| mock 通过但 Hermes 失败 | mock 不是产品链路；按 §2 / §3 同一架构验收 |
| 开发/生产两套方案？ | 只有 §0 一条链路；§6 是单元测试加速器 |
| 页面看不到 Hermes 调工具？ | 确认 Gateway 版本支持 `hermes.tool.progress`；跑 `test_hermes_stream.py`；标准/深度模式非 fast |
| 深度答案出现「估算」分项？ | 多为 **chat/completions 单轮** 在预检索摘要上幻觉；深度应走 Runs + 多轮 `orientg_kb_ask`；Tier 2 system 已禁止估算分项 |
| 标准模式却走 Tier 0？ | 旧版在 pack 够时降级本地；现已改为 **标准=固定 Tier 1**；仅 **快速** 或 **auto+覆盖够** 走 Tier 0 |
| 深度出现 `terminal: curl`？ | Hermes 未遵守 forbidden_tools；已对 Tier 2 同步禁 terminal；升级 Gateway 并检查 `orientg-kb-agent-policy.md` |
| 推理流 0、正文一次性出？ | 当前模型（如 qwen）可能无 `reasoning_content`；Runs 的 `message.delta` 也可能在 run 末批量推送，属上游行为 |
| Hermes 阶段 `orientg_kb_ask_calls=0`？ | Tier 1/2 会**自动补检索**；若本地重综合不如 Hermes（如全「缺少证据」），**保留 Hermes 原文**不 `replace_reply` |
| 深度模式 GPU 飙高 / 掉线？ | 深度链路过长：**预检索** + **Hermes Runs（多轮 MCP + 推理）** + 可能 **Orient-G 补检索 + 本地重综合**（同一张卡连续占满）。点 **停止** 会 cancel run 并跳过补检索；仍占用时请等 Gateway 收尾或重启 `hermes gateway` |
| 推理有字但无工具、很快结束？ | 查 Gateway/LLM 日志 `reasoning-budget` 是否耗尽；或模型未调用 MCP；`thinking_chars>0` 且 `tool_progress_events=0` 多为 budget/策略问题 |
| Windows 仍走 mock | 设 `HERMES_DEV_MOCK=false` 且 `HERMES_ENABLED=true` |

本机探活远程生产 API：`.\scripts\check_agent_remote.ps1 -BaseUrl "http://<内网>/api"`。

---

## 10. 仓库内 Hermes 相关文件索引

| 路径 | 用途 |
|------|------|
| `docs/hermes.md` | **本指南（唯一操作文档）** |
| `docs/finance-matrix-browser-testing.md` | 财务矩阵 Chrome DevTools / CDP 浏览器实测 |
| `docs/finance-agent-acceptance-matrix.md` | 42 条验收清单 + API Live 矩阵 |
| `docker-compose.hermes.yml` | 生产 Hermes overlay |
| `docker/hermes/env.hermes.example` | `.env.hermes` 模板 |
| `docker/hermes/mcp-orientg.snippet.json` | 生产 MCP（docker exec） |
| `docker/hermes/mcp-orientg.windows.example.yaml` | 开发 MCP 示例 |
| `docker/hermes/dotenv.hermes.orientg.example` | `~/.hermes/.env` JWT 示例 |
| `backend/mcp/orientg_server.py` | MCP 入口 |
| `backend/services/orientg_mcp_tools.py` | 工具实现 |
| `backend/services/hermes_client.py` | backend → Hermes HTTP |
