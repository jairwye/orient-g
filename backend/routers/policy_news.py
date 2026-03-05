from fastapi import APIRouter

router = APIRouter()


@router.get("/summary")
def policy_news_summary(limit: int = 5):
    """
    政策新闻摘要，供首页展示。
    由负责政策新闻细致页的员工实现真实数据。
    """
    # 占位
    return {
        "items": [
            {"id": "1", "title": "政策新闻占位标题", "date": "2025-03-01", "link": "/policy-news/1"},
        ]
    }
