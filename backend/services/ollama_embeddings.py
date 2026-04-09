from __future__ import annotations

from typing import Any

import httpx

from backend.config import settings
from backend.services.ollama_guard import post_json_with_guard


def embed_texts(texts: list[str], *, model: str | None = None, timeout_s: int = 60) -> list[list[float]]:
    """
    使用本地 Ollama 生成 embeddings。

    兼容：
    - /api/embed（新接口，支持 input 列表）
    - /api/embeddings（旧接口，通常一次一个 prompt）
    """
    if not settings.ollama_configured:
        raise RuntimeError("OLLAMA_URL 未配置，无法生成 embeddings")
    base = (settings.ollama_url or "").strip().rstrip("/")
    if not base:
        raise RuntimeError("OLLAMA_URL 为空")
    m = (model or settings.ollama_embed_model or "").strip()
    if not m:
        raise RuntimeError("ollama_embed_model 未配置")

    ins = [(t or "") for t in (texts or [])]
    if not ins:
        return []

    # 优先新接口：/api/embed
    url_embed = f"{base}/api/embed"
    url_old = f"{base}/api/embeddings"
    try:
        data_new = post_json_with_guard(
            url=url_embed,
            payload={"model": m, "input": ins},
            timeout_s=float(timeout_s),
            kind="embeddings.embed",
        )
        embs = data_new.get("embeddings") if isinstance(data_new, dict) else None
        if isinstance(embs, list) and all(isinstance(x, list) for x in embs):
            return [[float(v) for v in row] for row in embs]
    except Exception:
        pass

    # 回退旧接口：逐条请求 /api/embeddings
    out: list[list[float]] = []
    for t in ins:
        d2 = post_json_with_guard(
            url=url_old,
            payload={"model": m, "prompt": t},
            timeout_s=float(timeout_s),
            kind="embeddings.legacy",
        )
        emb = d2.get("embedding") if isinstance(d2, dict) else None
        if not isinstance(emb, list):
            raise RuntimeError("Ollama embeddings 响应缺少 embedding 字段")
        out.append([float(v) for v in emb])
    return out

