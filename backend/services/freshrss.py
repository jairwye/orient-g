"""
新闻政策页：FreshRSS GReader API 拉取，三类（游戏观点/游戏新闻/AI新闻）对应按钮 观点/新闻/AI。
每类内：合并 → 按时间新到旧排序 → 同时间打乱 → 取前 N 条；结果存内存缓存，不写数据库。
"""
import logging
import random
import time
from typing import Any, Optional
from urllib.parse import quote

import requests

from backend.config import settings

logger = logging.getLogger(__name__)

# 分类 label → 前端按钮 key（与方案一致）
LABEL_TO_BUTTON: dict[str, str] = {
    "游戏观点": "观点",
    "游戏新闻": "新闻",
    "AI新闻": "AI",
}
BUTTON_TO_LABEL = {v: k for k, v in LABEL_TO_BUTTON.items()}

# 内存缓存：{ "观点"|"新闻"|"AI": { "items": [...], "updated_at": float } }
_cache: dict[str, dict[str, Any]] = {}
_auth_token: Optional[str] = None
_last_error: Optional[str] = None
_last_success_at: Optional[float] = None


def _base_url(path: str) -> str:
    base = (settings.freshrss_api_url or "").rstrip("/")
    return f"{base}{path}" if path.startswith("/") else f"{base}/{path}"


def _login() -> bool:
    """ClientLogin 获取 Auth token。"""
    global _auth_token
    if not settings.freshrss_configured:
        return False
    try:
        url = _base_url("/accounts/ClientLogin")
        resp = requests.post(
            url,
            data={
                "Email": settings.freshrss_user,
                "Passwd": settings.freshrss_api_password,
            },
            headers={"User-Agent": "Orient-G/1.0"},
            timeout=15,
        )
        resp.raise_for_status()
        text = resp.text
        for line in text.splitlines():
            if line.startswith("Auth="):
                _auth_token = line.strip().split("Auth=", 1)[1]
                return True
        logger.warning("FreshRSS ClientLogin response missing Auth=: %s", text[:200])
        return False
    except Exception as e:
        logger.warning("FreshRSS ClientLogin failed: %s", e)
        _auth_token = None
        return False


def _stream_id_for_label(label: str) -> str:
    """该分类在 GReader 中的 stream id。"""
    return f"user/-/label/{label}"


def _item_belongs_to_stream(item: dict, stream_id: str, label: str) -> bool:
    """条目是否属于该 stream（按 directStreamIds 或 categories 判断）。"""
    label_suffix = f"label/{label}"
    for key in ("directStreamIds", "categories"):
        arr = item.get(key)
        if not isinstance(arr, list):
            continue
        for s in arr:
            if not isinstance(s, str):
                continue
            if s == stream_id or stream_id in s:
                return True
            if label_suffix in s or s.endswith(label):
                return True
    origin = item.get("origin")
    if isinstance(origin, dict):
        oid = origin.get("streamId")
        if oid == stream_id or (oid and (label_suffix in oid or oid.endswith(label))):
            return True
    return False


def _fetch_stream_page(
    label: str, continuation: Optional[str] = None
) -> tuple[list[dict], Optional[str]]:
    """
    拉取某分类的一页 stream/contents；仅保留属于该 label 的条目。
    返回 (本页条目列表, 下一页 continuation；无则 None)。
    """
    if not _auth_token:
        if not _login():
            return [], None
    stream_id = _stream_id_for_label(label)
    path = f"/reader/api/0/stream/contents?stream={quote(stream_id)}&n=100"
    if continuation:
        path += f"&c={quote(continuation)}"
    url = _base_url(path)
    try:
        resp = requests.get(
            url,
            headers={
                "Authorization": f"GoogleLogin auth={_auth_token}",
                "User-Agent": "Orient-G/1.0",
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items") if isinstance(data, dict) else []
        if not isinstance(items, list):
            items = []
        next_continuation = None
        if isinstance(data, dict) and data.get("continuation"):
            next_continuation = str(data["continuation"]).strip() or None
        filtered = [it for it in items if _item_belongs_to_stream(it, stream_id, label)]
        if len(filtered) != len(items):
            logger.debug("FreshRSS %s: filtered %d -> %d items", label, len(items), len(filtered))
        return filtered, next_continuation
    except Exception as e:
        logger.warning("FreshRSS stream/contents %s failed: %s", label, e)
        return [], None


def _published_ts(item: dict) -> int:
    """取条目的发布时间（秒），用于排序。"""
    for key in ("published", "timestampUsec", "crawlTimeMsec"):
        v = item.get(key)
        if v is not None:
            try:
                n = int(v)
                if key == "timestampUsec":
                    return n // 1_000_000
                if key == "crawlTimeMsec":
                    return n // 1000
                return n
            except (TypeError, ValueError):
                pass
    return 0


def _process_class(items: list[dict], max_items: int) -> list[dict]:
    """每类内：按时间新到旧排序，同时间打乱，取前 max_items 条。"""
    if not items:
        return []
    # 按 published 降序
    items = sorted(items, key=_published_ts, reverse=True)
    # 同时间打散：按时间分组，组内 shuffle 再按原顺序拼回
    by_ts: dict[int, list[dict]] = {}
    for it in items:
        ts = _published_ts(it)
        by_ts.setdefault(ts, []).append(it)
    result = []
    for ts in sorted(by_ts.keys(), reverse=True):
        group = by_ts[ts]
        random.shuffle(group)
        result.extend(group)
    return result[:max_items]


def _normalize_item(item: dict) -> dict:
    """归一化为前端所需字段；content 为完整 HTML，summary 为截断摘要。"""
    item_id = item.get("id") or ""
    title = (item.get("title") or "").strip()
    ts = _published_ts(item)
    from datetime import datetime
    published_iso = datetime.utcfromtimestamp(ts).strftime("%Y-%m-%dT%H:%M:%SZ") if ts else ""
    published_date = datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d") if ts else ""

    link = ""
    for alt in item.get("alternate") or []:
        if isinstance(alt, dict) and alt.get("href"):
            link = alt["href"]
            break
    if not link and isinstance(item.get("canonical"), list) and item["canonical"]:
        link = item["canonical"][0].get("href", "") if isinstance(item["canonical"][0], dict) else ""

    origin = item.get("origin") or {}
    origin_title = origin.get("title", "") if isinstance(origin, dict) else ""
    summary_obj = item.get("summary") or {}
    raw_content = summary_obj.get("content", "") if isinstance(summary_obj, dict) else (item.get("summary") or "")
    if not isinstance(raw_content, str):
        raw_content = ""

    thumbnail = ""
    enc = item.get("enclosure")
    if isinstance(enc, list) and enc and isinstance(enc[0], dict) and enc[0].get("href"):
        thumbnail = enc[0].get("href", "")
    if not thumbnail and raw_content:
        import re
        m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', raw_content)
        if not m:
            m = re.search(r'<img[^>]+data-src=["\']([^"\']+)["\']', raw_content)
        if m:
            thumbnail = m.group(1)

    return {
        "id": item_id,
        "title": title,
        "published": published_iso,
        "date": published_date,
        "link": link,
        "originTitle": origin_title,
        "summary": raw_content[:500] if raw_content else "",
        "content": raw_content,
        "thumbnail": thumbnail,
    }


def fetch_all() -> None:
    """拉取三个分类，每类处理管道后写入内存缓存。"""
    global _last_error, _last_success_at
    if not settings.freshrss_configured:
        _last_error = "FreshRSS 未配置"
        return
    labels_raw = (settings.freshrss_labels or "游戏观点,游戏新闻,AI新闻").strip()
    labels = [s.strip() for s in labels_raw.split(",") if s.strip()]
    if not labels:
        labels = list(LABEL_TO_BUTTON.keys())
    max_items = max(1, getattr(settings, "freshrss_max_items", 80))

    for label in labels:
        button = LABEL_TO_BUTTON.get(label, label)
        raw_items: list[dict] = []
        continuation: Optional[str] = None
        while True:
            page_items, continuation = _fetch_stream_page(label, continuation)
            raw_items.extend(page_items)
            if len(raw_items) >= max_items or not continuation:
                break
        processed = _process_class(raw_items, max_items)
        normalized = [_normalize_item(it) for it in processed]
        _cache[button] = {"items": normalized, "updated_at": time.time()}
        logger.info("FreshRSS %s (%s): %d items", label, button, len(normalized))

    _last_success_at = time.time()
    _last_error = None


def get_cached(category: Optional[str] = None) -> dict:
    """
    返回缓存。category 为 None 时返回所有分类；为 观点|新闻|AI 时只返回该分类。
    """
    if category:
        data = _cache.get(category, {"items": [], "updated_at": None})
        return {"categories": [category], "itemsByCategory": {category: data["items"]}, "lastSuccessAt": _last_success_at, "lastError": _last_error}
    categories = list(LABEL_TO_BUTTON.values())
    items_by = {c: _cache.get(c, {"items": [], "updated_at": None})["items"] for c in categories}
    return {"categories": categories, "itemsByCategory": items_by, "lastSuccessAt": _last_success_at, "lastError": _last_error}


def get_summary_items(limit: int = 5) -> list[dict]:
    """从缓存取摘要用条目（从「新闻」类取前 limit 条，若无则从任一类取）。"""
    for key in ("新闻", "观点", "AI"):
        data = _cache.get(key, {}).get("items", [])
        if data:
            return [{"id": it["id"], "title": it["title"], "date": it["date"], "link": it["link"]} for it in data[:limit]]
    return []


def get_item_by_id(item_id: str) -> Optional[dict]:
    """按 id 从缓存取单条（含完整 content）；用于详情页。"""
    for cat in ("观点", "新闻", "AI"):
        items = _cache.get(cat, {}).get("items", [])
        for it in items:
            if it.get("id") == item_id:
                return it
    return None
