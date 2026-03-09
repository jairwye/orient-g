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
