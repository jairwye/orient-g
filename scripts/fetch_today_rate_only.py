"""
仅拉取并写入当天汇率，不执行历史补全。用于快速排查「当天数据是否可写入」。
在项目根目录执行: .\.venv\Scripts\python.exe scripts\fetch_today_rate_only.py
"""
import datetime
import sys

# 保证 backend 可被导入
sys.path.insert(0, ".")

from backend.database import get_db
from backend.services.exchange_rates import _fetch_rate, _upsert

def main():
    today = datetime.date.today().strftime("%Y-%m-%d")
    print(f"拉取当天 {today} 汇率...")
    usd = _fetch_rate(today, "usd")
    eur = _fetch_rate(today, "eur")
    jpy = _fetch_rate(today, "jpy")
    print(f"  USD: {usd}, EUR: {eur}, JPY: {jpy}")
    if usd is None and eur is None and jpy is None:
        print("  全部拉取失败，未写入数据库。")
        return 1
    with get_db() as session:
        _upsert(session, today, usd, eur, jpy, 0)
    print(f"  已写入数据库。")
    return 0

if __name__ == "__main__":
    sys.exit(main())
