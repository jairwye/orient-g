# 知识库向量 RAG — 本地开发 setup

## 前置

- 本机 PostgreSQL（与 `DATABASE_URL` 一致）
- **pgvector 扩展**（Windows 默认安装通常没有，见下文）
- 远程 Ollama（可选）：`OLLAMA_URL` 指向内网生产机，且该机 `11434` 对开发机可达

## 一键检查

```powershell
.\scripts\setup-dev-kb-vector.ps1
```

或只建表：

```powershell
.\.venv\Scripts\python.exe scripts\init_kb_vector_local.py
```

## .env（本地开发示例）

```env
DATABASE_URL=postgresql://postgres:***@localhost:5432/mgmt_web
KB_VECTOR_ENABLED=true
OLLAMA_URL=http://<PROD_HOST>:11434
OLLAMA_EMBED_MODEL=bge-m3
KB_EMBEDDING_DIM=1024
DOCLING_MODE=http
DOCLING_HTTP_BASE_URL=http://<PROD_HOST>:8080/v1
AI_UPSTREAM_ALLOWED_HOSTS=localhost,127.0.0.1,::1,<PROD_HOST>
```

重启 backend 后，用 **admin** 账号调用：

```http
POST http://localhost:8000/api/knowledge/admin/reindex
Authorization: Bearer <登录接口返回的 JWT>
```

## Windows 安装 pgvector（PostgreSQL 18，推荐预编译包）

报错 `extension "vector" is not available` 时，**不必自己编译**。

### 方式 1：一键脚本（推荐）

1. **以管理员身份**打开 PowerShell（复制 DLL 到 `D:\Programs\PostgreSQL\18` 需要权限）
2. 在项目根目录执行：

```powershell
cd <PROJECT_ROOT>
powershell -ExecutionPolicy Bypass -File .\scripts\install-pgvector-windows.ps1
```

脚本会：下载 [pgvector PG18 Windows 预编译包](https://github.com/andreiramani/pgvector_pgsql_windows/releases) → 复制到 Postgres 目录 → 重启 `postgresql-x64-18` → 运行 `init_kb_vector_local.py`。

若 Postgres 不在 `D:\Programs\PostgreSQL\18`，先设置：

```powershell
$env:PGROOT = "你的PostgreSQL18目录"
```

### 方式 2：手动编译（仅当预编译包不可用）

1. 安装 Visual Studio **C++ 生成工具**
2. 以管理员打开 **x64 Native Tools Command Prompt**：

```cmd
set "PGROOT=D:\Programs\PostgreSQL\18"
cd %TEMP%
git clone --branch v0.8.2 https://github.com/pgvector/pgvector.git
cd pgvector
nmake /F Makefile.win
nmake /F Makefile.win install
```

3. 重启服务 **postgresql-x64-18**
4. 再运行 `scripts\init_kb_vector_local.py`

### 备选：仅开发库用 Docker（本机已装 Docker 时）

```powershell
docker run -d --name orient-g-pg-dev -e POSTGRES_PASSWORD=dev -e POSTGRES_DB=mgmt_web -p 5433:5432 pgvector/pgvector:pg16
```

`.env` 改为 `postgresql://postgres:dev@localhost:5433/mgmt_web` 后重新 init。

---

## 安装 pgvector 之后的本地操作流程

1. **确认 init 成功**

```powershell
.\.venv\Scripts\python.exe scripts\init_kb_vector_local.py
```

应看到 `[OK] CREATE EXTENSION vector` 与 `[OK] kb_doc_chunk_embeddings 表已就绪`。

2. **Ollama 嵌入（复用生产机）**

生产 Ollama 只监听 `127.0.0.1:11434` 时，开发机开隧道：

```powershell
ssh -L 11434:127.0.0.1:11434 <user>@<PROD_HOST>
```

`.env` 使用：

```env
OLLAMA_URL=http://127.0.0.1:11434
OLLAMA_EMBED_MODEL=bge-m3
KB_VECTOR_ENABLED=true
KB_EMBEDDING_DIM=1024
```

3. **启动本机 backend + frontend**

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn backend.main:app --reload
```

4. **为本机库文档建向量**（浏览器登录 http://localhost:3000 后取 JWT）

```powershell
curl.exe -s -X POST http://localhost:8000/api/auth/login -H "Content-Type: application/json" -d "{\"username\":\"admin\",\"password\":\"<YOUR_PASSWORD>\"}"
# 用返回的 token：
curl.exe -s -X POST http://localhost:8000/api/knowledge/admin/reindex -H "Authorization: Bearer <JWT>" -H "Content-Type: application/json" -d "{}"
```

5. **验证**

```powershell
.\.venv\Scripts\python.exe -c "from sqlalchemy import create_engine,text; from backend.config import settings; c=create_engine(settings.database_url).connect(); print(c.execute(text('SELECT embed_model,COUNT(*) FROM kb_doc_chunk_embeddings GROUP BY embed_model')).fetchall())"
```

本地与生产 **数据库分离**：生产 reindex 写生产库，本地 reindex 写本机 `mgmt_web`。

## 生产 reindex 注意

- **不要**访问 `:8000`：compose 未把 backend 映射到宿主机。
- 走 Caddy：**`http://<内网IP>/api/knowledge/admin/reindex`**（端口 80 或 443）。
- `Authorization: Bearer` 必须是 **`POST /api/auth/login` 返回的 `token`**（JWT），不是用户 ID 或密码。

```bash
# 在生产机或能访问 Caddy 的机器上
TOKEN=$(curl -s -X POST http://<PROD_HOST>/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"<YOUR_PASSWORD>"}' | jq -r .token)

curl -X POST http://<PROD_HOST>/api/knowledge/admin/reindex \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}'
```

或在生产机容器内（不经过 Caddy）：

```bash
docker compose exec backend python -c "
import httpx, os
# 更简单：本机 curl 127.0.0.1:8000 需先 exec 进 backend 网络命名空间
"
```

推荐在 **生产机** 上：

```bash
docker compose exec -T backend curl -s -X POST http://127.0.0.1:8000/api/knowledge/admin/reindex \
  -H "Authorization: Bearer YOUR_JWT" \
  -H "Content-Type: application/json" \
  -d '{}'
```

（JWT 仍须先通过 login 获取；可把 token 从浏览器开发者工具 sessionStorage 复制。）
