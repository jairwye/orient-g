from typing import Optional

from fastapi import APIRouter

from backend.services.exchange_rates import get_history, get_status

router = APIRouter()


@router.get("/status")
def exchange_status():
    """取数状态与进度，供前端展示。"""
    return get_status()


@router.get("/history")
def exchange_history(days: Optional[int] = None):
    """
    汇率历史，供汇率趋势页使用。返回从 2025-04-02 起的数据，适配 Recharts。
    days: 可选，最近 N 天；不传则返回全部。
    """
    data = get_history(days=days)
    return {"data": data}


@router.get("/summary")
def exchange_summary(days: int = 7):
    """
    汇率趋势摘要，供首页等展示。返回 labels + series（Recharts 可用）。
    """
    data = get_history(days=days)
    labels = [r["date"] for r in data]
    series = [
        {"name": "USD/CNY", "data": [r["usd"] for r in data]},
        {"name": "EUR/CNY", "data": [r["eur"] for r in data]},
        {"name": "JPY/CNY", "data": [r["jpy"] for r in data]},
    ]
    return {"labels": labels, "series": series}
