from fastapi import APIRouter, HTTPException

from backend.services.freshrss import get_cached, get_item_by_id, get_summary_items

router = APIRouter()

VALID_CATEGORIES = ("观点", "新闻", "AI")


@router.get("/list")
def policy_news_list(category: str | None = None):
    """
    新闻政策列表，按分类返回。category 为空返回全部三类；为 观点|新闻|AI 时只返回该分类。
    数据来自 FreshRSS 定时拉取的内存缓存。
    """
    if category and category not in VALID_CATEGORIES:
        category = None
    return get_cached(category)


@router.get("/item")
def policy_news_item(id: str = ""):
    """
    单条详情，含完整 content（HTML）；供详情页展示，原文链接仅于详情页提供。
    """
    if not id:
        raise HTTPException(status_code=400, detail="id required")
    item = get_item_by_id(id)
    if not item:
        raise HTTPException(status_code=404, detail="item not found")
    return item


@router.get("/summary")
def policy_news_summary(limit: int = 5):
    """
    政策新闻摘要，供首页展示。从同一份 FreshRSS 缓存取前 limit 条。
    """
    items = get_summary_items(limit=limit)
    if not items:
        return {"items": []}
    return {"items": items}
