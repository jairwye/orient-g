# Gitea 内网部署指南

## 概述

Orient-G 代码托管于内网 Gitea（HTTP），Container Registry 和 Actions 均运行在内网。

- **Gitea 地址**：`http://192.168.104.108:3090`
- **SSH 端口**：`2222`
- **组织**：`u1`
- **仓库**：`orient-g`

## 部署

```bash
cd ~/docker/gitea/
# 1. 准备 app.ini（见下方配置说明）
# 2. 启动
docker compose -f docker-compose.gitea.yml up -d
```

## app.ini 关键配置

```ini
[server]
PROTOCOL = http
DOMAIN = 192.168.104.108
HTTP_PORT = 3000
ROOT_URL = http://192.168.104.108:3090/
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

拉/push 内网 Registry 的机器需配 `insecure-registries`：

```json
{
  "insecure-registries": ["192.168.104.108:3090"]
}
```

## 认证

- **开发者 push**：SSH key 或 HTTPS PAT
- **生产机 pull**：Deploy key 或专用 machine user
- **act_runner**：Runner registration token（org 级）
