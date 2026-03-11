"""
汇率取数与入库逻辑，参考 jairwye/ex-rate。
数据源：fawazahmed0/currency-api，双 URL 多源轮询。
"""
import datetime
import logging
import time
from typing import Optional

import requests
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from backend.database import get_db

logger = logging.getLogger(__name__)

# 取数状态，供 /api/exchange/status 查询
_fetch_state: dict = {"fetching": False, "last_filled_date": None}


def get_status() -> dict:
    """返回取数状态与进度。"""
    try:
        with get_db() as session:
            row = session.execute(text("SELECT COUNT(*), MAX(date) FROM exchange_rates")).fetchone()
            total = row[0] or 0
            last_date = str(row[1]) if row[1] else None
    except OperationalError:
        total = 0
        last_date = None
    return {
        "fetching": _fetch_state["fetching"],
        "totalRecords": total,
        "lastFilledDate": _fetch_state.get("last_filled_date") or last_date,
    }


EXCHANGE_API_SOURCES = [
    "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@",
    "https://{date}.currency-api.pages.dev/v1/currencies/{currency}.json",
]
RATE_START_DATE = datetime.date(2025, 4, 2)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}


def _fetch_rate(date: str, currency: str) -> Optional[float]:
    """从外部 API 拉取指定日期、币种兑 CNY 汇率，多源轮询。"""
    currency = currency.lower()
    for api_base in EXCHANGE_API_SOURCES:
        try:
            if "cdn.jsdelivr.net" in api_base:
                url = f"{api_base}{date}/v1/currencies/{currency}.json"
            else:
                url = api_base.format(date=date, currency=currency)
            resp = requests.get(url, headers=HEADERS, timeout=10)
            if resp.status_code != 200:
                continue
            data = resp.json()
            if isinstance(data, dict) and currency in data and "cny" in data[currency]:
                rate = float(data[currency]["cny"])
                if rate > 0:
                    return rate
        except Exception as e:
            logger.debug("exchange api fail %s: %s", locals().get("url", api_base), e)
            continue
    return None


def _get_existing_row(session: Session, date: str) -> Optional[dict]:
    row = session.execute(
        text("SELECT date, usd_rate, eur_rate, jpy_rate FROM exchange_rates WHERE date = :d"),
        {"d": date},
    ).fetchone()
    if not row:
        return None
    return {"date": str(row[0]), "usd_rate": row[1], "eur_rate": row[2], "jpy_rate": row[3]}


def _upsert(session: Session, date: str, usd: Optional[float], eur: Optional[float], jpy: Optional[float], is_final: int) -> None:
    session.execute(
        text("""
        INSERT INTO exchange_rates (date, usd_rate, eur_rate, jpy_rate, is_final)
        VALUES (:d, :usd, :eur, :jpy, :fin)
        ON CONFLICT (date) DO UPDATE SET
          usd_rate = COALESCE(EXCLUDED.usd_rate, exchange_rates.usd_rate),
          eur_rate = COALESCE(EXCLUDED.eur_rate, exchange_rates.eur_rate),
          jpy_rate = COALESCE(EXCLUDED.jpy_rate, exchange_rates.jpy_rate),
          is_final = EXCLUDED.is_final
        """),
        {"d": date, "usd": usd, "eur": eur, "jpy": jpy, "fin": is_final},
    )
    session.commit()


def update_today_rate() -> None:
    """拉取当日 USD/EUR/JPY 写入库（is_final=0），并补全历史缺失。"""
    _fetch_state["fetching"] = True
    _fetch_state["last_filled_date"] = None
    try:
        today = datetime.date.today().strftime("%Y-%m-%d")
        usd = _fetch_rate(today, "usd")
        eur = _fetch_rate(today, "eur")
        jpy = _fetch_rate(today, "jpy")
        if usd is not None or eur is not None or jpy is not None:
            with get_db() as session:
                _upsert(session, today, usd, eur, jpy, 0)
            _fetch_state["last_filled_date"] = today
            logger.info("updated today rates %s: usd=%s eur=%s jpy=%s", today, usd, eur, jpy)
        check_and_fill_historical_data()
    except Exception as e:
        logger.exception("update_today_rate: %s", e)
    finally:
        _fetch_state["fetching"] = False


def finalize_today_data() -> None:
    """将当日记录标记为 is_final=1。"""
    try:
        today = datetime.date.today().strftime("%Y-%m-%d")
        with get_db() as session:
            session.execute(
                text("UPDATE exchange_rates SET is_final = 1 WHERE date = :d"),
                {"d": today},
            )
            session.commit()
        logger.info("finalized today %s", today)
    except Exception as e:
        logger.exception("finalize_today_data: %s", e)


def check_and_fill_historical_data() -> None:
    """从 RATE_START_DATE 到昨日，缺则补（is_final=1）。"""
    try:
        yesterday = datetime.date.today() - datetime.timedelta(days=1)
        if yesterday < RATE_START_DATE:
            return
        with get_db() as session:
            cur = RATE_START_DATE
            while cur <= yesterday:
                d = cur.strftime("%Y-%m-%d")
                row = _get_existing_row(session, d)
                need = row is None or row["usd_rate"] is None or row["eur_rate"] is None or row["jpy_rate"] is None
                if need:
                    usd = _fetch_rate(d, "usd")
                    eur = _fetch_rate(d, "eur")
                    jpy = _fetch_rate(d, "jpy")
                    if row:
                        usd = usd if usd is not None else row["usd_rate"]
                        eur = eur if eur is not None else row["eur_rate"]
                        jpy = jpy if jpy is not None else row["jpy_rate"]
                    if usd is not None or eur is not None or jpy is not None:
                        _upsert(session, d, usd, eur, jpy, 1)
                        _fetch_state["last_filled_date"] = d
                cur += datetime.timedelta(days=1)
                time.sleep(0.5)
    except Exception as e:
        logger.exception("check_and_fill_historical_data: %s", e)


def get_history(days: Optional[int] = None) -> list[dict]:
    """从库中读取历史，按 date 升序。days 为 None 表示全部（从 RATE_START_DATE 起）。DB 不可用时返回 []。"""
    try:
        today = datetime.date.today()
        start = RATE_START_DATE if days is None else max(RATE_START_DATE, today - datetime.timedelta(days=days))
        start_str = start.strftime("%Y-%m-%d")
        with get_db() as session:
            rows = session.execute(
                text("""
                SELECT date, usd_rate, eur_rate, jpy_rate
                FROM exchange_rates
                WHERE date >= :start
                ORDER BY date
                """),
                {"start": start_str},
            ).fetchall()
        return [
            {
                "date": str(r[0]),
                "usd": round(r[1], 4) if r[1] is not None else None,
                "eur": round(r[2], 4) if r[2] is not None else None,
                "jpy": round(r[3], 4) if r[3] is not None else None,
            }
            for r in rows
        ]
    except OperationalError:
        logger.debug("exchange_rates get_history: database unavailable")
        return []
