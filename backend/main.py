"""
Orient-G（财务信息内网）- 后端 API
职责：鉴权、Excel 解析与存储（经营数据当前为单文件，可扩展为入库）、经营/竞品/汇率/新闻 CRUD。
"""
import logging
import threading
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import OperationalError

from backend.config import settings
from backend.database import init_exchange_rates_table
from backend.routers import auth, health, exchange, policy_news, business, competitor, settings as settings_router
from backend.services.exchange_rates import finalize_today_data, update_today_rate
from backend.services.freshrss import fetch_all as freshrss_fetch_all

logger = logging.getLogger(__name__)
scheduler: BackgroundScheduler | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global scheduler
    try:
        init_exchange_rates_table()
        scheduler = BackgroundScheduler()
        scheduler.add_job(update_today_rate, "interval", hours=1)
        scheduler.add_job(finalize_today_data, "cron", hour=20, minute=0)
        if settings.freshrss_configured:
            interval_min = max(1, getattr(settings, "freshrss_fetch_interval_minutes", 10))
            scheduler.add_job(freshrss_fetch_all, "interval", minutes=interval_min)
        scheduler.start()
        # 首次拉取放后台，避免阻塞启动（历史补全可能需数分钟）
        def _run_initial_update():
            try:
                update_today_rate()
            except Exception as e:
                logger.warning("initial exchange rate update failed: %s", e)
        threading.Thread(target=_run_initial_update, daemon=True).start()
        if settings.freshrss_configured:
            def _run_initial_freshrss():
                try:
                    freshrss_fetch_all()
                except Exception as e:
                    logger.warning("initial FreshRSS fetch failed: %s", e)
            threading.Thread(target=_run_initial_freshrss, daemon=True).start()
    except OperationalError as e:
        from urllib.parse import urlparse
        try:
            parsed = urlparse(settings.database_url)
            db_info = f"{parsed.hostname or '?'}:{parsed.port or '?'}{parsed.path or ''}"
        except Exception:
            db_info = "(解析 DATABASE_URL 失败)"
        err_msg = str(getattr(e, "orig", e)) or repr(e)
        logger.warning(
            "PostgreSQL 不可用，汇率趋势功能已禁用。尝试连接: %s 错误: %s",
            db_info,
            err_msg,
        )
        logger.warning(
            "若错误为空，多为 Windows 下 PostgreSQL 非英文 locale 导致；"
            "请在 postgresql.conf 中设置 lc_messages = 'en_US' 或 'C' 并重启 PostgreSQL，详见 docs/汇率-PostgreSQL排查.md",
        )
    yield
    if scheduler:
        scheduler.shutdown(wait=False)


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
app.include_router(settings_router.router, prefix="/api/settings", tags=["settings"])
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
