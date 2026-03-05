from fastapi import APIRouter

router = APIRouter()


@router.get("/summary")
def exchange_summary(days: int = 7):
    """
    汇率趋势摘要，供首页展示。
    约定：返回 ECharts 可直接使用的 labels + series。
    由负责汇率趋势细致页的员工实现真实数据。
    """
    # 占位：固定示例数据
    return {
        "labels": ["2025-02-24", "2025-02-25", "2025-02-26"],
        "series": [{"name": "USD/CNY", "data": [7.19, 7.21, 7.20]}],
    }
