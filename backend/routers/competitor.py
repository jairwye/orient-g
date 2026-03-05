from fastapi import APIRouter

router = APIRouter()


@router.get("/summary")
def competitor_summary():
    """
    竞品财报摘要，供首页展示。
    由员工 X 实现。
    """
    # 占位
    return {
        "updatedAt": "2025-03-01",
        "items": [{"name": "竞品占位", "summary": "待维护", "link": "/competitor/1"}],
    }
