from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health():
    """供内网监控或负载均衡探测。"""
    return {"status": "ok"}
