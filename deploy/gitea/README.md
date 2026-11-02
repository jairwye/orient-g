# Gitea 内网部署指南

## 概述

Orient-G 代码托管于内网 Gitea（HTTP），Container Registry 和 Actions 均运行在内网。

下列地址/端口仅为**本机或运维文档填写处**；仓库内不写真实内网 IP。部署前在 `.env`（或本机环境）中设定：

| 变量 | 含义 | 示例占位 |
|------|------|----------|
| `GITEA_HOST` | Gitea 所在内网主机 | `<gitea-host>` |
| `GITEA_HTTP_HOST_PORT` | 宿主机 HTTP/Registry 端口 | `<http-port>` |
| `GITEA_SSH_HOST_PORT` | 宿主机 SSH 映射端口 | `<ssh-port>` |
| `POSTGRES_PASSWORD` | Gitea 库口令（必改） | （强随机） |

- **Gitea 地址**：`http://${GITEA_HOST}:${GITEA_HTTP_HOST_PORT}`
- **SSH**：`git@${GITEA_HOST}`，端口 `${GITEA_SSH_HOST_PORT}`
- **组织**：`u1`
- **仓库**：`orient-g`

## 部署

```bash
cd ~/docker/gitea/
# 1. 准备 .env（GITEA_* / POSTGRES_PASSWORD）与 app.ini
# 2. 启动
docker compose -f docker-compose.gitea.yml --env-file .env up -d
```

`.env` 示例（勿提交真实值）：

```env
GITEA_HTTP_HOST_PORT=<http-port>
GITEA_SSH_HOST_PORT=<ssh-port>
POSTGRES_USER=gitea
POSTGRES_PASSWORD=<strong-password>
POSTGRES_DB=gitea
```

## app.ini 关键配置

将 `<gitea-host>` / `<http-port>` 换成实际值；勿把填好真实地址的 `app.ini` 提交进本仓库。

```ini
[server]
PROTOCOL = http
DOMAIN = <gitea-host>
HTTP_PORT = 3000
ROOT_URL = http://<gitea-host>:<http-port>/
LOCAL_ROOT_URL = http://127.0.0.1:3000/

[session]
COOKIE_SECURE = false

[security]
INSTALL_LOCK = true

[packages]
ENABLED = true

[actions]
ENABLED = true
```

## Docker 客户端配置

拉/push 内网 Registry 的机器需配 `insecure-registries`（填实际主机与端口）：

```json
{
  "insecure-registries": ["<gitea-host>:<http-port>"]
}
```

## 认证

- **开发者 push**：SSH key 或 HTTPS PAT
- **生产机 pull**：Deploy key 或专用 machine user
- **act_runner**：Runner registration token（org 级；只放本机 `.env` / runner 配置，勿入库）
