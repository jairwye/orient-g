from __future__ import annotations

from urllib.parse import urlparse

from backend.config import settings


def _allowed_hosts() -> set[str]:
    raw = str(getattr(settings, "ai_upstream_allowed_hosts", "") or "")
    out: set[str] = set()
    for x in raw.split(","):
        h = x.strip().lower()
        if h:
            out.add(h)
    return out


def assert_upstream_allowed(url: str, *, service_name: str) -> None:
    """
    开发保护阀：默认仅允许本机/容器内服务名，阻止误把流量打到生产地址。
    需要放开时可在 .env 里设置：
    - AI_UPSTREAM_BLOCK_REMOTE=false（全局关闭）
    - 或把目标主机加入 AI_UPSTREAM_ALLOWED_HOSTS
    """
    if not bool(getattr(settings, "ai_upstream_block_remote", True)):
        return

    parsed = urlparse((url or "").strip())
    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise RuntimeError(f"{service_name} 地址无效：{url!r}")

    if host in _allowed_hosts():
        return

    raise RuntimeError(
        f"已阻止访问远程 {service_name} 地址：{url}。"
        "如确认安全，请在 .env 中将主机加入 AI_UPSTREAM_ALLOWED_HOSTS，"
        "或设置 AI_UPSTREAM_BLOCK_REMOTE=false。"
    )
