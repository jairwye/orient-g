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

脚本按依赖特性分别处理：**Python** 使用项目内 `.venv` 并安装后端依赖；**Node.js** 若未安装则通过 winget **全局安装**（不限制在项目目录）；前端依赖安装到 `frontend/node_modules`；复制 `.env.example` 为 `.env`、创建 `uploads`。PostgreSQL 需本机单独安装并创建数据库（脚本会检测并提示，详见参考/PostgreSQL安装与连接说明.md）。

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
   uvicorn backend.main:app --reload
   ```
3. 启动前端（新开终端）：`cd frontend; npm run dev`（Node 已通过一键安装全局安装）
4. 浏览器访问前端提示的地址（如 `http://localhost:3000`）。

## 目录结构

```
├── frontend/          # Next.js 前端（员工 X 负责首页、经营、竞品；他人负责汇率、政策新闻细致页）
├── backend/           # FastAPI 后端（鉴权、Excel、CRUD）
├── ai-bridge/         # 可选：AI 相关封装（当前仓库中未实现）
├── docs/              # 部署说明、API 契约（见 docs/api-contract.md）
├── scripts/           # 一键安装、部署用脚本
├── docker-compose.yml # 生产环境一键部署
└── README.md
```

## 生产部署

服务器上以 **docker-compose.yml** 方式运行，仅监听内网 IP。首次部署可在服务器上执行 `docker compose up -d`；若使用 Portainer 等工具，可上传 `docker-compose.yml` 并配置环境变量后一键部署。

**Caddy 相关**：反向代理 Caddy 通过卷挂载使用项目根目录的 `Caddyfile`，因此**必须在包含 Caddyfile 的目录下执行** `docker compose`（推荐：先克隆仓库，再在项目根目录执行）。若仅用 Portainer 粘贴 compose 而不克隆仓库，需在宿主机某路径（如 `/opt/mgmt-web/`）放置 `Caddyfile`，并在 compose 中把 `./Caddyfile` 改为该绝对路径。

**部署时务必配置的环境变量**（在 Portainer 的 Stack 环境变量或服务器 `.env` 中设置）：

- **BIND_IP**：反向代理绑定的内网 IP（如 `192.168.1.100`），生产环境必须设置，否则默认 `127.0.0.1` 仅本机可访问、内网其他机器无法访问。
- **POSTGRES_PASSWORD**：数据库密码；生产环境务必修改，勿使用默认值。
- **FRONTEND_ORIGIN**：浏览器实际访问的地址（如 `http://192.168.1.100` 或 `https://192.168.1.100`），用于后端 CORS。未设置时默认为 `http://localhost:3000`，若用户通过内网 IP 访问则跨域请求会被拒绝。
- **AUTH_SECRET**：页面登录 JWT 签名密钥；生产环境务必设置为强随机字符串，勿使用默认值，防止 token 被伪造。

## 扩展与协同

- 首页摘要所用 API 约定见 [docs/api-contract.md](docs/api-contract.md)。
- 经营数据为**根路径 /**，`/business` 重定向至 `/`；其他细致页：`/competitor`、`/exchange`、`/policy-news`。财务后台默认路径为 `/admin`，可在后台页面修改。
- 项目更新记录见 [CHANGELOG.md](CHANGELOG.md)。当前版本 **1.1**：多用户与登录鉴权、管理后台布局、关闭标签页需重新登录等见 CHANGELOG。
