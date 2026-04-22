#!/usr/bin/env bash
# 可选：由 cron 或 systemd timer 周期性执行。若经 Caddy 的健康检查失败，则 force-recreate caddy 服务。
# 用法：
#   ORIENT_G_COMPOSE_DIR=/home/jair/docker/orient-g ./scripts/caddy-health-recreate.sh
#   ./scripts/caddy-health-recreate.sh /home/jair/docker/orient-g
#
# 要求：目录内同时存在 docker-compose.yml 与 Caddyfile（与 README 生产部署约定一致）。

set -euo pipefail

COMPOSE_DIR="${1:-${ORIENT_G_COMPOSE_DIR:-}}"
if [[ -z "${COMPOSE_DIR}" ]]; then
  echo "用法: ORIENT_G_COMPOSE_DIR=/path/to/orient-g $0" >&2
  echo "  或: $0 /path/to/orient-g" >&2
  exit 1
fi

if [[ ! -f "${COMPOSE_DIR}/docker-compose.yml" ]]; then
  echo "错误: 未找到 ${COMPOSE_DIR}/docker-compose.yml" >&2
  exit 1
fi
if [[ ! -f "${COMPOSE_DIR}/Caddyfile" ]]; then
  echo "错误: 未找到 ${COMPOSE_DIR}/Caddyfile" >&2
  exit 1
fi

cd "${COMPOSE_DIR}"

BIND_IP="127.0.0.1"
if [[ -f .env ]]; then
  # 取首个未注释的 BIND_IP= 行
  line="$(grep -E '^[[:space:]]*BIND_IP=' .env 2>/dev/null | head -1 || true)"
  if [[ -n "${line}" ]]; then
    val="${line#*=}"
    val="${val//\"/}"
    val="${val//\'/}"
    val="$(echo "${val}" | tr -d '[:space:]')"
    [[ -n "${val}" ]] && BIND_IP="${val}"
  fi
fi

try_health() {
  local url="$1"
  curl -sf --max-time 4 "${url}" >/dev/null 2>&1
}

# 依次探测：按 BIND_IP、本机回环、常见内网绑定 0.0.0.0 时回环仍可能通
if try_health "http://${BIND_IP}/api/health"; then
  exit 0
fi
if try_health "http://127.0.0.1/api/health"; then
  exit 0
fi

echo "$(date -Iseconds) Caddy 健康检查失败，执行: docker compose up -d --force-recreate caddy" >&2
docker compose up -d --force-recreate caddy
