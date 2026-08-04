"""横比主体代号（公开仓仅占位符；生产真实名经 env 扩展，勿写入仓库）。

Canonical：
- PRIMARY_ENTITY = YYCQ（本公司）
- PEER_ENTITY = 可比公司A

生产在 `.env`（gitignore）设置：
  KB_COMPARE_ENTITY_EXTRA_MARKERS=逗号分隔的额外匹配名
即可匹配内网 KB / 用户问句中的真实主体，而无需把全称提交到 GitHub。
"""

from __future__ import annotations

import os
import re
from functools import lru_cache

PRIMARY_ENTITY = "YYCQ"
PEER_ENTITY = "可比公司A"

_DEFAULT_MARKERS: tuple[str, ...] = (PRIMARY_ENTITY, PEER_ENTITY, "本公司")


def _split_csv(raw: str | None) -> list[str]:
    if not raw:
        return []
    out: list[str] = []
    for part in str(raw).split(","):
        s = part.strip()
        if s and s not in out:
            out.append(s)
    return out


def clear_compare_entity_cache() -> None:
    compare_entity_markers.cache_clear()
    primary_aliases.cache_clear()
    peer_aliases.cache_clear()


@lru_cache(maxsize=1)
def compare_entity_markers() -> tuple[str, ...]:
    from backend.config import settings

    extra = _split_csv(getattr(settings, "kb_compare_entity_extra_markers", None))
    if not extra:
        extra = _split_csv(os.environ.get("KB_COMPARE_ENTITY_EXTRA_MARKERS"))
    ordered: list[str] = []
    for m in (*_DEFAULT_MARKERS, *extra):
        if m and m not in ordered:
            ordered.append(m)
    return tuple(ordered)


@lru_cache(maxsize=1)
def primary_aliases() -> tuple[str, ...]:
    """本公司侧匹配名（含 YYCQ / 本公司 + EXTRA 中归入 primary 的项由调用方用 is_primary）。"""
    from backend.config import settings

    extra = _split_csv(getattr(settings, "kb_compare_entity_primary_aliases", None))
    if not extra:
        extra = _split_csv(os.environ.get("KB_COMPARE_ENTITY_PRIMARY_ALIASES"))
    ordered: list[str] = [PRIMARY_ENTITY, "本公司"]
    for m in extra:
        if m not in ordered:
            ordered.append(m)
    return tuple(ordered)


@lru_cache(maxsize=1)
def peer_aliases() -> tuple[str, ...]:
    from backend.config import settings

    extra = _split_csv(getattr(settings, "kb_compare_entity_peer_aliases", None))
    if not extra:
        extra = _split_csv(os.environ.get("KB_COMPARE_ENTITY_PEER_ALIASES"))
    ordered: list[str] = [PEER_ENTITY, "PeerA"]
    for m in extra:
        if m not in ordered:
            ordered.append(m)
    return tuple(ordered)


def _aliases_re(aliases: tuple[str, ...]) -> str:
    parts = [re.escape(a) for a in aliases if a]
    return "|".join(parts) if parts else re.escape(PRIMARY_ENTITY)


def primary_match_re() -> str:
    return _aliases_re(primary_aliases())


def peer_match_re() -> str:
    return _aliases_re(peer_aliases())


def is_primary_text(text: str) -> bool:
    t = text or ""
    if not t:
        return False
    if re.search(primary_match_re(), t, re.I):
        return True
    # 公开仓短码
    return bool(re.search(r"\bYYCQ\b", t, re.I))


def is_peer_text(text: str) -> bool:
    t = text or ""
    if not t:
        return False
    return bool(re.search(peer_match_re(), t, re.I))


def canonical_primary() -> str:
    return PRIMARY_ENTITY


def canonical_peer() -> str:
    return PEER_ENTITY


def structure_table_title() -> str:
    return f"{PRIMARY_ENTITY} vs {PEER_ENTITY} · 2025 人员结构对比"
