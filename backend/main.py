"""
Orient-G（财务信息内网）- 后端 API
职责：鉴权、Excel 解析与存储（经营数据当前为单文件，可扩展为入库）、经营/竞品/汇率/新闻 CRUD。
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings
from backend.routers import health, exchange, policy_news, business, competitor


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时可选：建表、检查 DB 连接等
    yield
    # 关闭时清理
    pass


app = FastAPI(
    title="Orient-G 财务信息内网 API",
    description="内网仅用，经营数据、竞品财报、汇率、政策新闻",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, tags=["health"])
app.include_router(exchange.router, prefix="/api/exchange", tags=["exchange"])
app.include_router(policy_news.router, prefix="/api/policy-news", tags=["policy-news"])
app.include_router(business.router, prefix="/api/business", tags=["business"])
app.include_router(competitor.router, prefix="/api/competitor", tags=["competitor"])
