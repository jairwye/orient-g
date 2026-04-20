# Orient-G（财务信息内网）

内网/局域网财务信息展示页，提供经营数据摘要、竞品财报、汇率趋势、政策新闻等服务。仅内网部署，不暴露公网。项目及 GitHub 仓库名称：**Orient-G**。

**使用对象**：相关人通过展示页查看经营数据、竞品、汇率、政策新闻等；财务人员通过独立后台页面上传经营数据 Excel，后台入口仅内网可用、不向展示端暴露。

## 本地开发环境要求

- **Git for Windows**：clone、提交、提 PR
- **Node.js**（LTS）：前端依赖与 `npm run dev`。一键安装中若未检测到则通过 **winget 全局安装**（不适合限制在项目目录）。
- **Python 3.10+**：后端 FastAPI；一键安装使用项目内 **.venv**（适合项目内部署）。
- **PostgreSQL**：本机安装，本地开发连接 `localhost:5432`（与生产 Docker 内 PostgreSQL 分离）

## 一键安装（推荐）

在项目根目录执行：

```powershell
.\scripts\setup.ps1
```

脚本按依赖特性分别处理：**Python** 使用项目内 `.venv` 并安装后端依赖；**Node.js** 若未安装则通过 winget **全局安装**（不限制在项目目录）；前端依赖安装到 `frontend/node_modules`；复制 `.env.example` 为 `.env`、创建 `uploads`。PostgreSQL 需本机单独安装并创建数据库（脚本会检测并提示）；连接与排查见 [docs/汇率-PostgreSQL排查.md](docs/汇率-PostgreSQL排查.md)。

## 手动安装

```powershell
# 后端
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt

# 前端
cd frontend; npm install; cd ..

# 配置
copy .env.example .env
# 编辑 .env，填写数据库连接等
```

## 本地配置

1. 复制环境变量：`copy .env.example .env`
2. 编辑 `.env`：
   - `DATABASE_URL`：指向本机 PostgreSQL（如 `postgresql://user:pass@localhost:5432/mgmt_web`）
   - `UPLOAD_DIR`：本地上传目录（如 `./uploads`），该目录已加入 `.gitignore`；财务后台路径、登录用户名等应用设置保存在该目录下的 `app_settings.json`，请勿删除
   - `DB_MIGRATION_MODE`：数据库结构迁移模式。`legacy`=启动自动建表（默认）；`alembic`=由 Alembic 显式迁移管理（生产推荐）
3. 在 PostgreSQL 中创建数据库（若尚未创建）：
   ```sql
   CREATE DATABASE mgmt_web;
   ```
4. 后端首次运行时可自动建表（见后端 README 或启动脚本）。

## 启动顺序

1. 确保本机 **PostgreSQL 服务已启动**。
2. 在**项目根目录**启动后端（保证 `UPLOAD_DIR` 解析一致，应用设置才能持久保存）：
   ```powershell
   .\.venv\Scripts\Activate.ps1
   # 推荐：以模块方式启动，避免路径/导入问题
   python -m uvicorn backend.main:app --reload
   ```
3. 启动前端（新开终端）：`cd frontend; npm run dev`（Node 已通过一键安装全局安装）
4. 浏览器访问前端提示的地址（如 `http://localhost:3000`）。

## 代码质量与验证（推荐开发习惯）

在 `frontend/` 下：

- **CI/合并门槛（严格）**：`npm run lint`（等价于 `npm run lint:strict`，要求 0 warnings）
- **开发快速检查**：`npm run lint:fast`
- **质量巡检（不阻断 CI）**：`npm run lint:quality`
  - 本仓库采用“档 2”策略：`lint:quality` 会对 `@typescript-eslint/no-explicit-any` 给出 **warning**。
  - **新增代码禁止引入 `any`**：优先用 `unknown` + 类型守卫/窄化替代，存量逐步清理。

在仓库根目录：

- **后端测试**：`python -m pytest -q`

## 数据库结构迁移（Alembic，生产推荐）

本仓库已引入 Alembic 用于**只迁移数据库结构（schema）**。建议生产环境使用：

### 总体流程（先备份，再迁移）

1. **备份数据库**（备份方式二选一：方案 1 / 方案 2；两种都做更稳）。
2. **设置迁移模式**：`DB_MIGRATION_MODE=alembic`（避免应用启动时隐式建表/补列）。
3. **执行 Alembic 迁移**（执行方式二选一：A / B）。
4. **重启与验证**：重启 `backend` 后访问 `/api/health`，并抽查关键页面/接口。

> 说明：这里的 **方案 1/2** 只是在讲“如何备份”；**A/B** 只是在讲“在哪里执行 alembic 命令”。二者可以组合，不是四选一。

### Step 1：生产备份怎么做（备份方式二选一）

#### 方案 1：`pg_dump`（推荐，可移植、可回滚）

本仓库 `docker-compose.yml` 里的数据库服务名是 `db`，并且使用以下环境变量：
`POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_DB`。

在 **compose 同目录** 执行（会在宿主机当前目录生成备份文件）：

```bash
# 生成带时间戳的备份文件（自定义路径即可）
BK="backup_$(date +%Y%m%d_%H%M%S).dump"

# 以自定义格式备份（推荐：体积更小、恢复更灵活）
docker compose exec -T db pg_dump -U "${POSTGRES_USER:-mgmt}" -d "${POSTGRES_DB:-mgmt_web}" -Fc > "$BK"

echo "备份完成：$BK"
```

恢复（回滚）示例：

```bash
# 1) 先停止 backend（避免写入）
docker compose stop backend

# 2) 如需“完全覆盖恢复”，建议先清空并重建 schema（谨慎！确认是要覆盖）
docker compose exec -T db psql -U "${POSTGRES_USER:-mgmt}" -d "${POSTGRES_DB:-mgmt_web}" -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"

# 3) 用 pg_restore 恢复
BK="backup_xxx.dump"  # 替换为你的备份文件
cat "$BK" | docker compose exec -T db pg_restore -U "${POSTGRES_USER:-mgmt}" -d "${POSTGRES_DB:-mgmt_web}" --clean --if-exists

# 4) 再启动 backend
docker compose up -d backend
```

说明：
- `-T`：避免 `docker compose exec` 分配伪终端，配合重定向更稳定。
- `-Fc`：自定义格式（`pg_restore` 使用），更适合生产备份/恢复。

#### 方案 2：volume snapshot（最快，但不可移植）

如果你的 PostgreSQL 数据卷是 `pgdata`（compose 里就是这个名字），可以用 **宿主机/云盘/存储** 的快照能力做卷快照。
这个方式恢复很快，但通常只能在同一套存储/同一台机器上恢复，不如 `pg_dump` 可移植。

### Step 2：设置迁移模式（必做）

在同目录 `.env` 或 Portainer 的环境变量里设置：

- `DB_MIGRATION_MODE=alembic`

### Step 3：执行迁移（执行方式二选一）

#### A) Docker / Portainer（推荐）

本仓库生产 `docker-compose.yml` 会把 `DATABASE_URL` 注入到 `backend` 容器（指向 `db:5432`）。因此直接在容器内执行：

```bash
docker compose exec backend alembic -c backend/alembic.ini upgrade head
```

迁移完成后再做 `docker compose up -d`（或重启 backend）即可。

#### B) 本机虚拟环境（仅用于本地开发）

在项目根目录执行迁移（使用与你本机后端相同的 `.env` / `DATABASE_URL`）：

```powershell
.\.venv\Scripts\Activate.ps1
alembic -c backend\alembic.ini upgrade head
```

然后再启动/更新后端容器或服务。

## Windows 开发注意事项（含中文路径）

- **命令执行目录**：建议始终在项目根目录运行后端命令，并先激活 `.venv`。
- **推荐启动方式**：使用 `python -m ...`（如上文的 `python -m uvicorn ...`、或 `python -m backend.main`），在 Windows/PowerShell + 含中文路径场景更稳。
- **若 PowerShell 出现 `Command failed to spawn: Aborted`**：优先检查是否在正确目录、是否已激活 `.venv`；尽量避免在同一条命令里使用复杂的引号/花括号拼接。

## 目录结构

```
├── frontend/          # Next.js 前端（员工 X 负责首页、经营、竞品；他人负责汇率、政策新闻细致页）
├── backend/           # FastAPI 后端（鉴权、Excel、CRUD）
├── docs/              # 部署说明、API 契约、汇率 PostgreSQL 排查（见 docs/api-contract.md、docs/汇率-PostgreSQL排查.md）
├── 规则/              # 项目规则与约束（不上传 GitHub）
├── 规划/              # 实现规划、待更新计划、各功能方案与清单（不上传 GitHub）
├── scripts/           # 一键安装、部署用脚本（如 setup.ps1）
├── docker-compose.yml # 生产环境一键部署
├── Caddyfile         # 反向代理配置，生产部署时与 compose 同目录
├── .env.example       # 环境变量示例（复制为 .env 后修改，.env 已加入 .gitignore）
├── CHANGELOG.md      # 版本更新记录
└── README.md
```

## 生产部署

服务器上以 **docker-compose.yml** 方式运行，仅监听内网 IP。首次部署可在服务器上执行 `docker compose up -d`；若使用 Portainer 等工具，可上传 `docker-compose.yml` 并配置环境变量后一键部署。

**Caddy 相关**：反向代理 Caddy 通过卷挂载使用项目根目录的 `Caddyfile`，因此**必须在包含 Caddyfile 的目录下执行** `docker compose`（推荐：先克隆仓库，再在项目根目录执行）。若仅用 Portainer 粘贴 compose 而不克隆仓库，需在宿主机某路径（如 `/opt/mgmt-web/`）放置 `Caddyfile`，并在 compose 中把 `./Caddyfile` 改为该绝对路径。

**更新业务镜像（`docker compose pull`）**：`docling` 在 compose 中为**本地 build** 镜像，且配置了 `pull_policy: never`，**不应**从任何 registry 拉取；无仓库前缀的短名若被误 pull，会被解析为 `docker.io/library/...`，既不存在又易触发镜像站限流。日常只更新后端/前端等 registry 镜像时，在 compose 所在目录执行：

```bash
docker compose pull db backend frontend caddy
```

需要更新 Ollama 时再单独执行（镜像较大，可与上面拆开、错峰执行，减轻镜像站 429）：

```bash
docker compose pull ollama
```

若仍使用整栈 `docker compose pull`，在含本仓库 `docker-compose.yml` 的前提下，`docling` 会被跳过拉取；**勿**为仅存在于本机的 tag 单独配置成「无 registry 前缀的 `image:` 且不带 `pull_policy: never`」，否则 `pull` 会去 Docker Hub/镜像站并报错。

**Docker 守护进程经 HTTP 代理拉镜像（如 nihomo）**：`docker compose pull` 由 **dockerd** 出站，仅在 shell 里 `export http_proxy` **通常无效**。若要让拉镜像走本机 nihomo，需在 nihomo 中开启 **mixed（或 HTTP）入站端口**（常见为 `7890`），并为 systemd 管理的 Docker 服务注入代理环境变量，例如 Linux 下：

1. 创建目录：`/etc/systemd/system/docker.service.d/`
2. 新建 `proxy.conf`（端口按本机 nihomo 实际 mixed 端口修改）：

```ini
[Service]
Environment="HTTP_PROXY=http://127.0.0.1:7890"
Environment="HTTPS_PROXY=http://127.0.0.1:7890"
Environment="NO_PROXY=localhost,127.0.0.1,::1"
```

`NO_PROXY` 中可按需加入内网 registry 主机名，避免内网镜像误走代理。

3. 执行：`sudo systemctl daemon-reload && sudo systemctl restart docker`

之后在同一台机器上执行的 `docker pull` / `docker compose pull` 会由守护进程经代理访问外网 registry。代理可缓解部分网络问题；若镜像站仍返回 **429 Too Many Requests**，可配合 **Docker Hub 登录**（`docker login`）、换镜像源或错峰分服务拉取。

**Docling sidecar 镜像单独构建**（`docker/docling-sidecar/Dockerfile` 的构建上下文为该目录本身，勿在子目录内使用错误的 `COPY` 路径）：

- 在仓库根目录：`docker build -f docker/docling-sidecar/Dockerfile -t orientg-docling-sidecar:temp docker/docling-sidecar`
- 或进入目录后：`cd docker/docling-sidecar && docker build -t orientg-docling-sidecar:temp .`

Compose 中 `docling` 服务已配置 `build.context: docker/docling-sidecar`、默认 `image: orientg-docling-sidecar:local` 与 **`pull_policy: never`**（避免误从 registry 拉取）。`docker compose build docling` 会将构建结果打为该镜像名；若你沿用 README 下方的 `-t orientg-docling-sidecar:temp`，在 `.env` 中设置 `DOCLING_IMAGE=orientg-docling-sidecar:temp` 与手工 tag 对齐即可。

Sidecar Dockerfile 与 [Docling 官方镜像](https://github.com/docling-project/docling/blob/main/Dockerfile) 对齐思路：基础镜像为 **`python:3.12-slim-bookworm`**、`pip` 使用 **`--extra-index-url https://download.pytorch.org/whl/cpu`**、环境变量 `HF_HOME`/`TORCH_HOME`/`OMP_NUM_THREADS`。构建参数 **`SKIP_MODEL_DOWNLOAD` 默认为 `1`**：默认**不**执行 `docling-tools models download`（避免构建期访问 Hugging Face；首次解析时再由运行时拉取或挂载缓存）。若需与官方一致把模型打进镜像，构建时传 **`--build-arg SKIP_MODEL_DOWNLOAD=0`**（需联网；镜像更大）。并与 **生产环境 GPU 由 Ollama 独占** 的约定一致：`docling` 服务不申请 GPU，文档解析走 CPU。

Docling 构建常见问题的**排查顺序**推荐如下：

1. **确认 `apt-get` 阶段是否通过**：若日志在 `apt-get update` / `apt-get install` 时报 `Network error` / `connection abort`，可按下文的 `DEBIAN_MIRROR` 配置切换 Debian 源。
2. **若失败在 `pip install` 阶段**：
   - 优先在构建时启用国内 PyPI 源（不会影响运行时，只影响镜像构建期的 pip 下载源）；例如：
     ```bash
     DOCKER_BUILDKIT=1 docker build \
       --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
       -t orientg-docling-sidecar:temp .
     ```
   - 若仍频繁出现 `Network error: Software caused connection abort` / `BrokenPipeError`，建议：
     - 在构建命令中增加 `HTTP_PROXY` / `HTTPS_PROXY` 相关 build-arg，或在网络更稳定的机器上构建再推送镜像；
     - 或使用下文的「可选：离线构建优化（本地 wheels）」方案，在宿主机提前下载好依赖后再构建。

若构建机网络对 PyPI/CDN 不稳定（即使小 wheel 也会 Broken pipe），可在构建时注入 PyPI 镜像/代理（不会影响运行时，只影响镜像构建期的 pip 下载源）：

```bash
DOCKER_BUILDKIT=1 docker build \
  --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
  -t orientg-docling-sidecar:temp .
```

如需附加源，可再传：`--build-arg PIP_EXTRA_INDEX_URL=...`（例如公司内网的 Nexus/Artifactory Python proxy）。

若 **`apt-get` 阶段**出现 `Network error` / `connection abort`（访问 `deb.debian.org` 不稳定），可在构建时指定 Debian 镜像根（**不要**带尾部的 `/debian`，Dockerfile 会自动拼 `/debian` 与 `/debian-security`）：

```bash
DOCKER_BUILDKIT=1 docker build \
  --build-arg DEBIAN_MIRROR=https://mirrors.tuna.tsinghua.edu.cn \
  -t orientg-docling-sidecar:temp .
```

使用 `docker compose build docling` 时，可在项目根 `.env` 中设置 `DEBIAN_MIRROR=https://mirrors.tuna.tsinghua.edu.cn`（与 `PIP_INDEX_URL` 可同时使用）。

**可选：离线构建优化（本地 wheels，但不入库）**

当构建机对 PyPI/CDN 的网络极不稳定时，可选择在宿主机提前下载好 Docling 依赖的 wheels，再由 Docker 构建优先从本地 wheels 安装，减少构建期的联网需求。

1. 在 `docker/docling-sidecar/` 下，使用约定的本地缓存目录 `vendor/docling-wheels/`（目录已在该路径下的 `.gitignore` 中忽略，仅允许保留 `.gitignore` / `.gitkeep` 等少量占位文件，不会把大体积 wheels 提交到仓库）。
2. 在宿主机上执行一次预下载（示例）：
   ```bash
   cd docker/docling-sidecar
   python -m venv .venv
   # Windows 下改用 .venv\Scripts\Activate.ps1
   . .venv/bin/activate
   pip install --upgrade pip
   pip download -r requirements.txt -d vendor/docling-wheels
   ```
3. 构建 Docling 镜像时，显式启用本地 wheels 优先路径：
   ```bash
   DOCKER_BUILDKIT=1 docker build \
     --build-arg USE_LOCAL_WHEELS=1 \
     -t orientg-docling-sidecar:temp .
   ```
   当 `USE_LOCAL_WHEELS=1` 且构建上下文中存在 `vendor/docling-wheels/` 时，Dockerfile 会优先通过 `--no-index --find-links=/wheels` 从该目录安装依赖，并继续使用官方的 PyTorch CPU wheel 源；否则退回在线安装逻辑（含国内 PyPI 源配置与重试策略）。

若 Caddy 启动或 reload 时提示 `input is not formatted`，请用**官方格式化工具**在已部署环境中执行一次，挂载的 Caddyfile 会被原地格式化，可将更新后的文件提交到仓库以消除后续警告：

```bash
docker compose exec caddy caddy fmt --overwrite /etc/caddy/Caddyfile
```

**部署时务必配置的环境变量**（在 Portainer 的 Stack 环境变量或服务器 `.env` 中设置）：

- **BIND_IP**：反向代理绑定的内网 IP（如 `192.168.1.100`），生产环境必须设置，否则默认 `127.0.0.1` 仅本机可访问、内网其他机器无法访问。
- **POSTGRES_PASSWORD**：数据库密码；生产环境务必修改，勿使用默认值。
- **FRONTEND_ORIGIN**：浏览器实际访问的地址（如 `http://192.168.1.100` 或 `https://192.168.1.100`），用于后端 CORS。未设置时默认为 `http://localhost:3000`，若用户通过内网 IP 访问则跨域请求会被拒绝。
- **AUTH_SECRET**：页面登录 JWT 签名密钥；生产环境务必设置为强随机字符串，勿使用默认值，防止 token 被伪造。

## 开发/生产与 Ollama（GPU）

- **生产环境约定**：`docker-compose.yml` 中启用 Ollama 时，由 **Ollama 容器独占 GPU**（`deploy.resources.reservations.devices` 等），用于推理；**Docling sidecar 仅 CPU**，不与 Ollama 争用 GPU。单机单卡时请勿再给 `docling`/`backend` 挂载 NVIDIA 设备。
- **Ollama 与 GPU 为可选**：流程文档生成等 AI 能力依赖 Ollama；未配置 `OLLAMA_URL` 时，相关功能会提示「未配置」或返回 503，其余功能（经营数据、汇率、新闻、知识库等）正常可用。
- **开发机无 GPU、生产机有 GPU 且同一局域网**：可在开发环境 `.env` 中设置 `OLLAMA_URL=http://生产机内网IP:11434`，让开发环境复用生产机上的 Ollama（需生产机开放 11434 仅对内网或指定 IP）。这样开发时无需在本机跑 GPU，也不需在开发机做 GPU 相关测试。
- **从 GitHub 克隆使用的用户**：可不配置 Ollama，直接使用非 AI 功能；若本机或局域网内有 Ollama 实例，在 `.env` 中设置 `OLLAMA_URL` 即可启用流程文档等 AI 功能。CI/自动化测试可不包含依赖 GPU 或 Ollama 的用例。

## Docling 长任务与队列治理

- 文档解析与大 PDF 任务已切换为**持久化队列**（`kb_tasks`），worker 重启后会自动续跑 `queued/running` 任务，不再依赖进程内内存队列。
- 大 PDF 建议保留较大的 `DOCLING_HTTP_TIMEOUT_S`（例如 600~1800），避免 OCR 中途被误杀；同时配合租约心跳防止“长任务卡死”。
- 推荐同时配置以下参数（见 `.env.example`）：
  - `QUEUE_WORKER_LEASE_SECONDS`、`QUEUE_WORKER_HEARTBEAT_SECONDS`
  - `QUEUE_RUNNING_TIMEOUT_SECONDS`、`QUEUE_QUEUED_TIMEOUT_SECONDS`
  - `QUEUE_TASK_MAX_ATTEMPTS`、`QUEUE_RETRY_BACKOFF_SECONDS`
  - `DOCLING_HTTP_CONNECT_TIMEOUT_S`、`DOCLING_HTTP_READ_TIMEOUT_S`、`DOCLING_HTTP_MAX_RETRIES`
- 运行中可通过 `GET /api/queue/stats` 观察持久化队列状态（`persisted_tasks`）与当前 worker 执行情况。
- 若上游 Docling 不可达，任务会按退避策略重试；超过重试上限后会进入 `failed`，前端可看到失败状态与错误摘要。

## 扩展与协同

- 首页摘要所用 API 约定见 [docs/api-contract.md](docs/api-contract.md)。
- 经营数据为**根路径 /**，`/business` 重定向至 `/`；其他细致页：`/competitor`、`/exchange`、`/policy-news`、`/knowledge`（知识库展位）、`/utils`（实用工具，含流程文档 `/utils/process-doc`、大 PDF 生知识库、「数据解析」等）。其中「数据解析」入口当前沿用路径 `/utils/excel-kanban`，目标是：用户上传电子表，通过 LLM + 工具（Prompt/MCP 风格工具/Skills 等）对表格数据进行解析，生成可视化看板、整理为更符合逻辑和条理的表格视图，并完成信息归纳、专业评价与风险识别。财务后台默认路径为 `/admin`，可在后台页面修改。
- **股权全景（实验）**：`/equity` 及关联分析页用于内网导入后的公司股权架构与地理等可视化；**为临时增加能力，后续可能移除**，接口与页面行为以当前版本为准、不作为长期对外契约。
- 项目更新记录见 [CHANGELOG.md](CHANGELOG.md)。当前版本 **1.2.1.1**：股权全景实验能力、文档与规划修正等见 CHANGELOG。

## 知识库（权限/共享）验收说明

本轮新增「用户上传文档 → 共享到不同知识库类型 → AI/知识库页按 ACL 检索」的链路。权限语义要点：

- **owner 永远可读**：文档归属任何知识库类型，所有者都能检索/阅读。
- **MultiDept/MultiProject**：文档共享到该类型时选择的部门/项目成员可读（按文档的 `share_scope` 生效）。

### 推荐验收路径

- **管理后台**：`/admin`
  - 确认「知识库类型 · 默认可读勾选」里每个 `kb_kind` 的默认勾选与预期一致，且「文档所有者」始终勾选且置灰。
  - 确认「特殊知识库文档 · 读权限勾选」里 Multi* 文档会显示只读的共享范围（部门/项目）。
- **知识库页**：`/knowledge`
  - 上传文档 → 列表可见 → 删除可用
  - 共享到（Dept/Project/Multi*）→ 再用不同账号登录验证可见性
- **AI 互动页**：`/ai-interaction`
  - 上传文档后，默认写入“我的私人知识库”；点击加载/刷新知识库范围后进行 ask 验证可检索

### 测试账号（用于权限覆盖面验证）

以下账号用于覆盖部门成员/部门负责人/项目成员/项目负责人及 Multi* 组合场景（默认密码以管理后台实际创建为准）：

- `u_fin_1`：财务部成员
- `u_rd_1`：研发部成员
- `u_proj2_1`：proj2 项目成员
- `u_rd_lead`：研发部负责人
- `u_proj3_member`：proj3 项目成员
- `u_proj3_lead`：proj3 项目负责人
