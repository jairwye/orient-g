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


def canonicalize_compare_entity(phrase: str) -> str:
    """将别名/真实名归一到公开 canonical（YYCQ / 可比公司A）。"""
    s = (phrase or "").strip()
    if not s:
        return s
    if s in (PRIMARY_ENTITY, PEER_ENTITY):
        return s
    if is_primary_text(s):
        return PRIMARY_ENTITY
    if is_peer_text(s):
        return PEER_ENTITY
    return s


@lru_cache(maxsize=1)
def compare_entity_markers() -> tuple[str, ...]:
    from backend.config import settings

    extra = _split_csv(getattr(settings, "kb_compare_entity_extra_markers", None))
    if not extra:
        extra = _split_csv(os.environ.get("KB_COMPARE_ENTITY_EXTRA_MARKERS"))
    primary_extra = _split_csv(getattr(settings, "kb_compare_entity_primary_aliases", None))
    if not primary_extra:
        primary_extra = _split_csv(os.environ.get("KB_COMPARE_ENTITY_PRIMARY_ALIASES"))
    peer_extra = _split_csv(getattr(settings, "kb_compare_entity_peer_aliases", None))
    if not peer_extra:
        peer_extra = _split_csv(os.environ.get("KB_COMPARE_ENTITY_PEER_ALIASES"))
    ordered: list[str] = []
    for m in (*_DEFAULT_MARKERS, *extra, *primary_extra, *peer_extra):
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


def user_facing_entity_labels(user_query: str) -> dict[str, str]:
    """问句中出现的展示名：canonical → 用户用语（检索仍用 YYCQ/可比公司A）。"""
    q = (user_query or "").strip()
    if not q:
        return {}
    out: dict[str, str] = {}
    # 较长别名优先，避免短码抢占
    for alias in sorted(primary_aliases(), key=len, reverse=True):
        if alias and alias in q and alias not in (PRIMARY_ENTITY, "本公司"):
            out[PRIMARY_ENTITY] = alias
            break
    if PRIMARY_ENTITY not in out:
        for alias in primary_aliases():
            if alias and alias in q:
                out[PRIMARY_ENTITY] = alias
                break
    for alias in sorted(peer_aliases(), key=len, reverse=True):
        if alias and alias in q and alias not in (PEER_ENTITY, "PeerA"):
            out[PEER_ENTITY] = alias
            break
    if PEER_ENTITY not in out:
        for alias in peer_aliases():
            if alias and alias in q:
                out[PEER_ENTITY] = alias
                break
    return out


def present_entity_label(canonical: str, user_query: str = "") -> str:
    """对外展示名：优先用户问句用语，否则回落 canonical。"""
    can = (canonical or "").strip()
    if not can:
        return can
    if is_primary_text(can) or can == PRIMARY_ENTITY:
        key = PRIMARY_ENTITY
    elif is_peer_text(can) or can == PEER_ENTITY:
        key = PEER_ENTITY
    else:
        key = canonicalize_compare_entity(can)
    labels = user_facing_entity_labels(user_query)
    return labels.get(key) or (
        PRIMARY_ENTITY if key == PRIMARY_ENTITY else PEER_ENTITY if key == PEER_ENTITY else can
    )


def _collapse_stacked_present_label(text: str, label: str) -> str:
    """去掉「主体（主体）」/「主体主体」叠名。"""
    lab = (label or "").strip()
    if not lab or not text:
        return text or ""
    esc = re.escape(lab)
    t = re.sub(rf"{esc}\s*[（(]\s*{esc}\s*[）)]", lab, text)
    t = re.sub(rf"(?<![一-龥A-Za-z0-9]){esc}{esc}(?![一-龥A-Za-z0-9])", lab, t)
    return t


def rewrite_reply_present_entity_labels(reply: str, user_query: str = "") -> str:
    """终稿后处理：把内部代称还原为问句实体名（仅当问句含非 canonical 别名）。"""
    labels = user_facing_entity_labels(user_query)
    if not labels:
        return reply or ""
    text = reply or ""
    peer = labels.get(PEER_ENTITY)
    primary = labels.get(PRIMARY_ENTITY)
    # 先消「可比公司A（展示名）」类括号映射，避免盲替换后叠名
    if peer and peer != PEER_ENTITY:
        esc_p = re.escape(peer)
        text = re.sub(
            rf"可比公司A\s*[（(]\s*(?:即用户所称)?\s*{esc_p}\s*[）)]",
            peer,
            text,
        )
        text = re.sub(rf"{esc_p}\s*[（(]\s*可比公司A\s*[）)]", peer, text)
        text = text.replace(PEER_ENTITY, peer)
        text = re.sub(r"\bPeerA\b", peer, text)
        text = _collapse_stacked_present_label(text, peer)
    if primary and primary != PRIMARY_ENTITY:
        esc_y = re.escape(primary)
        text = re.sub(
            rf"(?:YYCQ|本公司)\s*[（(]\s*(?:即用户所称)?\s*{esc_y}\s*[）)]",
            primary,
            text,
            flags=re.I,
        )
        text = re.sub(rf"{esc_y}\s*[（(]\s*(?:YYCQ|本公司)\s*[）)]", primary, text, flags=re.I)
        text = re.sub(r"\bYYCQ\b", primary, text, flags=re.I)
        # 「本公司」仅在表头/标题语境替换，避免误伤「本公司侧口径」类说明时可接受整体替换为问句名
        if "本公司" != primary and "本公司" in text and primary in (user_query or ""):
            text = text.replace("本公司", primary)
        text = _collapse_stacked_present_label(text, primary)
    return text


def structure_table_title(user_query: str = "") -> str:
    primary = present_entity_label(PRIMARY_ENTITY, user_query)
    peer = present_entity_label(PEER_ENTITY, user_query)
    return f"{primary} vs {peer} · 2025 人员结构对比"
