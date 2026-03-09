"""
数据库连接与汇率表。与 config.database_url（PostgreSQL）一致，启动时建表。
"""
import logging
from contextlib import contextmanager
from typing import Generator
from urllib.parse import urlparse, urlunparse

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from backend.config import settings

logger = logging.getLogger(__name__)
Base = declarative_base()


def _normalize_database_url(url: str) -> str:
    """去掉 path 中多余斜杠，避免 localhost:5432//mgmt_web 导致连接失败。"""
    try:
        p = urlparse(url)
        path = p.path.replace("//", "/").strip() or "/"
        return urlunparse((p.scheme, p.netloc, path, p.params, p.query, p.fragment))
    except Exception:
        return url


engine = create_engine(
    _normalize_database_url(settings.database_url),
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_exchange_rates_table() -> None:
    """若 exchange_rates 表不存在则创建。"""
    sql = """
    CREATE TABLE IF NOT EXISTS exchange_rates (
        date DATE PRIMARY KEY,
        usd_rate REAL,
        eur_rate REAL,
        jpy_rate REAL,
        is_final INTEGER DEFAULT 0
    )
    """
    with engine.connect() as conn:
        conn.execute(text(sql))
        conn.commit()
    logger.info("exchange_rates table ready")


@contextmanager
def get_db() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
