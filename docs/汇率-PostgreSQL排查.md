# 汇率趋势页 PostgreSQL 连接排查

当启动日志出现「PostgreSQL 不可用，汇率趋势功能已禁用」且汇率页无数据时，按下面步骤逐项排查。

---

## 0. 错误信息为空时：用命令行直连看真实报错

在 Windows 上 psycopg2 有时只报 `OperationalError` 且无文字说明。可在**项目根目录**、**先激活 .venv** 后执行下面命令，直接看到真实错误（如「连接被拒」「密码认证失败」等）：

```bash
python -c "from backend.config import settings; import psycopg2; psycopg2.connect(settings.database_url)"
```

（会使用项目根目录下的 `.env` 中的 `DATABASE_URL`，与后端启动时一致。）

若仍只显示 `psycopg2.OperationalError` 无文字，可运行脚本打出异常详情（含 errno 等）：

```bash
python scripts/check_db_connect.py
```

**Windows 上无错误文案时**：多为 PostgreSQL 使用非英文 locale，导致 psycopg2 无法解码错误消息。请直接看 **第 7 节**，在 `postgresql.conf` 中设置 `lc_messages = 'en_US'` 并重启 PostgreSQL 后即可看到具体错误。也可先尝试把 `.env` 里的 `localhost` 改成 `127.0.0.1`。

- 若报 `Connection refused`：PostgreSQL 未启动或未监听 5432。
- 若报 `password authentication failed for user "xxx"`：用户名或密码错误，或需在 `.env` 里对密码做 URL 编码。
- 若报 `database "mgmt_web" does not exist`：需先创建数据库。
- 若命令能正常结束无报错：说明连接正常，问题可能在应用加载环境或其它环节。

---

## 1. 看启动日志里的「尝试连接」信息

日志会打印：`尝试连接: 主机:端口/数据库名`。

- **若出现双斜杠**，例如 `localhost:5432//mgmt_web`  
  - 说明 `.env` 里的 `DATABASE_URL` 在数据库名前面多写了 `/`。  
  - **正确格式**：`postgresql://用户名:密码@主机:端口/数据库名`（主机和数据库名之间**只有一个** `/`）。  
  - 修改 `.env`，把 `...5432//mgmt_web` 改成 `...5432/mgmt_web`，保存后重启后端。  
  - 代码已做容错：会尽量把 path 里的 `//` 规范成 `/`，若仍失败请以修正 `.env` 为准。

- **若显示的是默认值** `user:password@localhost:5432/mgmt_web`  
  - 说明没有读到 `.env` 里的 `DATABASE_URL`。  
  - 请在**项目根目录**（即包含 `backend`、`.env` 的目录）执行：  
    `uvicorn backend.main:app --reload`  
  - 确认项目根下存在 `.env` 文件，且其中有 `DATABASE_URL=...` 一行。

---

## 2. 确认 DATABASE_URL 格式

在项目根目录的 `.env` 中，应有一行类似：

```env
DATABASE_URL=postgresql://用户名:密码@localhost:5432/mgmt_web
```

注意：

- **用户名、密码**：与 PostgreSQL 里实际创建的用户一致；密码里若包含 `@`、`#`、`:`、`/` 等特殊字符，需 [URL 编码](https://en.wikipedia.org/wiki/Percent-encoding)（如 `@` → `%40`）。
- **主机**：本机用 `localhost` 或 `127.0.0.1`；若 PostgreSQL 在其它机器，改为该机 IP 或主机名。
- **端口**：默认 `5432`，若改过端口要一致。
- **数据库名**：必须是已存在的库（如 `mgmt_web`）；主机和数据库名之间**只一个** `/`，不要写成 `//mgmt_web`。

改完 `.env` 后保存，并重新启动后端。

---

## 3. 确认 PostgreSQL 已启动并监听

- **Windows**  
  - 服务：`Win + R` → `services.msc` → 找到「postgresql-x64-xx」→ 状态应为「正在运行」。  
  - 或命令行（在 PostgreSQL 的 bin 目录下或已加入 PATH）：  
    `pg_isready -h localhost -p 5432`  
    若显示 `accepting connections` 表示服务正常。

- **Linux / macOS**  
  - `pg_isready -h localhost -p 5432`  
  - 或：`sudo systemctl status postgresql`（以实际服务名为准）。

若 `pg_isready` 失败，先解决 PostgreSQL 未启动或未监听 5432 的问题（安装、启动、监听地址/端口）。

---

## 4. 用同一套账号、库名测试登录

用你配置的「用户名」和「数据库名」在命令行连一次，确认能连上且能建表：

```bash
psql -h localhost -p 5432 -U 你的用户名 -d mgmt_web
```

- 若提示「数据库 mgmt_web 不存在」：  
  先用默认库连上（如 `psql -h localhost -U postgres -d postgres`），执行：  
  `CREATE DATABASE mgmt_web;`  
  再重试上面命令。

- 若提示密码错误：  
  修正 `.env` 里的 `DATABASE_URL` 中的密码；如有特殊字符，记得 URL 编码。

- 能连上后，可在 `psql` 里执行：  
  `CREATE TABLE IF NOT EXISTS exchange_rates (date DATE PRIMARY KEY, usd_rate REAL, eur_rate REAL, jpy_rate REAL, is_final INTEGER DEFAULT 0);`  
  若报「没有权限」，说明该用户没有在该库下建表权限，需用超级用户授权或换用有权限的用户。

---

## 5. 检查 pg_hba.conf（本机仍连不上时）

若以上都正确，但应用仍连不上，可能是 PostgreSQL 的认证配置不允许该方式连接。

- 找到 `pg_hba.conf`（Windows 多在安装目录的 `data` 下，Linux 常见 `/etc/postgresql/*/main/pg_hba.conf`）。
- 确保有对应用户从本机连接的规则，例如：  
  `host    mgmt_web    你的用户名    127.0.0.1/32    md5`  
  或：  
  `host    all    all    127.0.0.1/32    md5`
- 修改后重启 PostgreSQL 服务，再重启后端。

---

## 6. 小结对照表

| 现象 | 可能原因 | 处理 |
|------|----------|------|
| 日志里 `localhost:5432//mgmt_web`（双斜杠） | DATABASE_URL 中库名前多了一个 `/` | 把 `...5432//mgmt_web` 改为 `...5432/mgmt_web` |
| 日志里是默认 `user:password@...` | 未读到 .env | 在项目根目录启动、确认有 `.env` 和 `DATABASE_URL` |
| 密码错误 / 认证失败 | 密码错误或未 URL 编码 | 修正 DATABASE_URL 中的密码 |
| 数据库不存在 | 未建 mgmt_web 库 | 用超级用户执行 `CREATE DATABASE mgmt_web;` |
| 没有建表权限 | 用户无 CREATE 权限 | 授权或换用有权限的用户 |
| 服务未启动 / 未监听 | PostgreSQL 未跑或端口不对 | 启动服务、用 pg_isready 确认端口 |

按上述步骤修正后，重启后端；若连接成功，日志会出现「exchange_rates table ready」和「updated today rates ...」，汇率页会逐渐有数据（依赖定时拉取）。

---

## 7. psycopg2 报空 OperationalError（Windows 常见）

若端口通、但 `python scripts/check_db_connect.py` 和 uvicorn 都只报 `OperationalError ()` 无文字，这是 **psycopg2 在 Windows 上的已知问题**：当 PostgreSQL 使用**非英文 locale**（如中文、法文）时，服务端错误消息解码失败，Python 端就看不到具体原因。

**解决办法（推荐）**：在 PostgreSQL 配置里把错误消息语言改为英文：

1. **找到 postgresql.conf**：
   - **Windows**：一般在安装目录的 `data` 下，例如 `C:\Program Files\PostgreSQL\15\data\postgresql.conf`（15 换成你的主版本号，如 14、16）。若不确定，可用 psql 查：连上任意库后执行 `SHOW config_file;` 会打出完整路径。
   - **本机服务对应目录**：任务管理器 → 服务 → 找到 postgresql-x64-xx → 右键属性可看“可执行文件路径”，其上级目录的 `..\data\postgresql.conf` 即为配置所在。
2. 用记事本或其它编辑器打开，修改或新增一行：`lc_messages = 'en_US'`（若无 en_US 可用 `lc_messages = 'C'`）。
3. 保存后**重启 PostgreSQL 服务**。
4. 再运行 `python scripts/check_db_connect.py` 或启动 uvicorn，此时应能看到具体错误文案，再按提示修正。

参考：[psycopg2 #417](https://github.com/psycopg/psycopg2/issues/417)、[psycopg2 #1442](https://github.com/psycopg/psycopg2/issues/1442)。

**仍可先用 psql 排查**：`psql -h 127.0.0.1 -p 5432 -U 你的用户名 -d mgmt_web`，按提示输入密码。若 psql 能连上而 Python 仍不能，改完 `lc_messages` 后 Python 端应会显示与 psql 一致的错误信息。

---

## 8. 生产环境：页面提示「暂无汇率数据，请稍后或检查后端定时任务」时如何排查

页面上出现该提示说明前端拿到的历史数据为空（`/api/exchange/history` 返回的 `data` 为空或请求失败）。按下面顺序排查。

### 8.1 直接请求后端接口

**含义**：用浏览器或命令行直接访问后端 API，看返回是空数据、报错还是正常有数据。

**具体做法：**

1. **确定「后端地址」**  
   即浏览器访问生产站点的域名或 IP（例如 `http://192.168.1.100` 或 `https://mgmt.company.com`）。前端请求的是「同一站点下的 /api/...」，所以后端地址就是该站点的协议+主机+端口（如有），例如 `http://192.168.1.100:80` 或 `https://mgmt.company.com`。

2. **用浏览器**  
   - 打开新标签页，访问：`你的后端地址/api/exchange/history`  
   - 再访问：`你的后端地址/api/exchange/status`  
   看页面显示的 JSON：`data` 是否为空数组、是否有 `fetching`/`totalRecords` 等。

3. **用命令行（可选）**  
   - **Linux / macOS / Git Bash**：在终端执行（把 `http://192.168.1.100` 换成你的后端地址）：
     ```bash
     curl -s "http://192.168.1.100/api/exchange/history"
     curl -s "http://192.168.1.100/api/exchange/status"
     ```
   - **Windows PowerShell**：
     ```powershell
     Invoke-RestMethod -Uri "http://192.168.1.100/api/exchange/history"
     Invoke-RestMethod -Uri "http://192.168.1.100/api/exchange/status"
     ```
     若未安装 curl 也可用：`(Invoke-WebRequest -Uri "http://192.168.1.100/api/exchange/history").Content`

**如何判断结果：**

- 返回 **502、连接失败、超时**：后端未启动或网络/反向代理有问题，需先让后端可访问。
- 返回 **200 且内容为 `{"data":[]}`**：接口正常但库里没有数据，继续 8.2、8.3。
- 返回 **200 且 `data` 里有数组且非空**：接口和库都正常，问题多半在前端请求的地址或缓存，可强制刷新（Ctrl+F5）或清缓存后再试。

---

### 8.2 看后端启动日志

**含义**：通过日志确认数据库是否连上、调度器是否启动、是否有「exchange_rates table ready」或报错。

**具体做法：**

- **本机直接运行 uvicorn 时**：在启动后端的那个终端/控制台里看输出。启动瞬间会打印 PostgreSQL 相关提示；若有报错会直接出现在同一窗口。
- **Docker 部署时**：  
  1. 查后端容器名：`docker ps` 或 `docker compose ps`，找到运行 FastAPI/uvicorn 的容器（名称可能是 `orient-g-backend`、`backend` 等，以你实际 compose/运行名为准）。  
  2. 看最近日志：`docker logs 容器名 --tail 200`，或 `docker compose logs backend --tail 200`。  
  3. 在日志中搜索：`PostgreSQL`、`exchange_rates table ready`、`汇率趋势功能已禁用`、`updated today rates`、`OperationalError` 等。

**如何判断：**

- 出现 **「PostgreSQL 不可用，汇率趋势功能已禁用」**：数据库未连上，调度器未启动，不会拉取也不会写库，需按本文档第 0～7 节排查 PostgreSQL 连接。
- 出现 **「exchange_rates table ready」**：说明建表/连接正常；若页面仍无数据，继续 8.3 查库里是否真有数据。

---

### 8.3 确认数据库是否有数据

**含义**：直接查 PostgreSQL 里 `exchange_rates` 表是否有行，确认后端用的库和当前连的是否一致。

**具体做法：**

任选一种能执行 SQL 的方式（在能连上生产 PostgreSQL 的机器上操作）：

**方式 A：psql 命令行**

```bash
# 格式：psql -h 主机 -p 端口 -U 用户名 -d 数据库名
# 示例（按你实际的主机、端口、用户名、库名改）：
psql -h 192.168.1.100 -p 5432 -U postgres -d mgmt_web
# 按提示输入密码后，在 psql 里执行：
SELECT COUNT(*), MIN(date), MAX(date) FROM exchange_rates;
```

**方式 B：Docker 内 PostgreSQL**

若数据库在 Docker 里（例如服务名为 `db` 或 `postgres`）：

```bash
docker exec -it 数据库容器名 psql -U postgres -d mgmt_web -c "SELECT COUNT(*), MIN(date), MAX(date) FROM exchange_rates;"
```

或先进入容器再执行：

```bash
docker exec -it 数据库容器名 bash
psql -U postgres -d mgmt_web
# 在 psql 里执行：
SELECT COUNT(*), MIN(date), MAX(date) FROM exchange_rates;
```

**方式 C：图形化工具（如 pgAdmin、DBeaver）**

连上生产 PostgreSQL，选中数据库（如 `mgmt_web`），打开 SQL 窗口，执行：

```sql
SELECT COUNT(*), MIN(date), MAX(date) FROM exchange_rates;
```

**如何判断：**

- **COUNT = 0**：表里没有数据，从未写入成功。结合 8.2 的日志看：若启动时报了 PostgreSQL 不可用，先修连接；若已出现「exchange_rates table ready」仍为 0，可能是定时任务还没跑到或拉取三方 API 失败，可再查日志里是否有 `updated today rates` 或异常。
- **COUNT > 0**：库里有数据。若 8.1 里接口仍返回空，多半是后端用的 **DATABASE_URL** 和当前查的库不一致（例如连了别的库或别的库名），需要核对生产环境里后端容器的 `DATABASE_URL` 与当前连接的库、库名是否一致。

---

### 8.4 核对生产环境 DATABASE_URL（Docker 时）

**含义**：确认后端实际连的是哪个库，和 8.3 里查的是不是同一个。

**具体做法：**

- **Docker Compose**：看 compose 里后端服务的 `environment` 或 `env_file`，找到 `DATABASE_URL`。或在宿主机执行：
  ```bash
  docker exec 后端容器名 env | findstr DATABASE_URL
  ```
  （Linux/mac 下把 `findstr` 换成 `grep`，例如 `docker exec 后端容器名 env | grep DATABASE_URL`）
- 对比 8.3 中你连接的：主机、端口、数据库名、用户名是否与 `DATABASE_URL` 里一致。若不一致，要么改环境变量让后端连到有数据的库，要么在正确的库里执行 8.3 的 SQL 再对比接口返回。

---

### 8.5 Docker 部署时其他注意点

- 后端容器的 **DATABASE_URL** 必须指向可访问的 PostgreSQL：若数据库在宿主机，用宿主机 IP 或 `host.docker.internal`（Windows/Mac），不要用 `localhost`（在容器内 localhost 是容器自己）。
- 若数据库与后端在同一 compose 内，一般用**服务名**作主机名（如 `postgres`、`db`）。
- **密码与 volume 一致性**：PostgreSQL 官方镜像只在**首次初始化数据目录**时用 `POSTGRES_PASSWORD` 创建用户并设密码，之后密码写在 volume（如 `pgdata`）里；修改 `.env` 中的 `POSTGRES_PASSWORD` 并重启容器**不会**更新库里已有用户的密码。若你改过 `.env` 后出现 `password authentication failed for user "mgmt"`，说明 backend 用的是新密码、库里仍是旧密码。解决方式二选一：（1）在库里把密码改成与当前 `.env` 一致：`docker exec -it 数据库容器名 psql -U mgmt -d mgmt_web -c "ALTER USER mgmt PASSWORD '你的新密码';"`，并确保生产环境 `.env` 中 `POSTGRES_PASSWORD` 与该密码一致后重启 backend；（2）将 `.env` 的 `POSTGRES_PASSWORD` 改回首次部署时使用的密码。compose 中 db 与 backend 共用同一套 `POSTGRES_USER`/`POSTGRES_PASSWORD` 环境变量，两边理论上一致，不一致多因 volume 曾用旧密码初始化导致。
- 查看后端日志：`docker logs 后端容器名 --tail 200` 或 `docker compose logs backend --tail 200`，确认是否有「exchange_rates table ready」「updated today rates」或 PostgreSQL/API 相关报错。

### 8.6 小结

| 现象 | 可能原因 | 建议 |
|------|----------|------|
| /history 返回 502 或无法访问 | 后端未起或网络/代理问题 | 检查后端进程、反向代理、防火墙 |
| /history 返回 200 且 data 为空 | 库无数据或后端连错库 | 查启动日志是否报 DB 错误；查库中 COUNT(*)；核对 DATABASE_URL |
| 启动日志报 PostgreSQL 不可用 / password authentication failed | 数据库连接失败；Docker 下常见为 .env 改过密码但 volume 仍为旧密码 | 按第 0～7 节排查；Docker 见 8.5「密码与 volume 一致性」，用 ALTER USER 或改回 .env 密码 |
| 库有数据但页面仍无 | 前端请求的并非该后端或缓存 | 核对前端请求的 API 基地址、清缓存或强制刷新 |
