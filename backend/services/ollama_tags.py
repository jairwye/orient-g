from __future__ import annotations

from typing import Any

import httpx

from backend.config import settings


def list_models() -> list[dict[str, Any]]:
    """
    读取 Ollama 本地模型列表（/api/tags）。
    返回 items: [{id,label,size_bytes?,modified_at?}, ...]
    """
    base = (settings.ollama_url or "").strip().rstrip("/")
    if not base:
        return []
    url = f"{base}/api/tags"
    try:
        with httpx.Client(timeout=5.0) as client:
            r = client.get(url)
            r.raise_for_status()
            data = r.json()
    except Exception:
        return []
    models = data.get("models") if isinstance(data, dict) else None
    if not isinstance(models, list):
        return []
    out: list[dict[str, Any]] = []
    for m in models:
        if not isinstance(m, dict):
            continue
        name = str(m.get("name") or "").strip()
        if not name:
            continue
        out.append(
            {
                "id": name,
                "label": name,
                "size_bytes": m.get("size"),
                "modified_at": m.get("modified_at"),
            }
        )
    return out

