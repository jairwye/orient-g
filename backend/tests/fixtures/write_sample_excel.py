"""
生成手测用 Excel（经营数据 + 月份/利润/营收），供浏览器上传验证「电子表数据解析」工作流。
用法：在项目根目录执行
  python backend/tests/fixtures/write_sample_excel.py
输出：backend/tests/fixtures/sample_finance.xlsx
"""

from __future__ import annotations

import io
from pathlib import Path

try:
    import openpyxl
except ImportError as e:
    raise SystemExit("需要安装 openpyxl：pip install openpyxl") from e


def main() -> None:
    root = Path(__file__).resolve().parent
    out = root / "sample_finance.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "经营数据"
    ws.append(["月份", "净利润", "营业收入"])
    for row in [
        ["2024-01", 100, 1000],
        ["2024-02", 200, 1200],
        ["2024-03", 150, 1100],
    ]:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    data = buf.getvalue()
    out.write_bytes(data)
    print(f"written {out} ({len(data)} bytes)")


if __name__ == "__main__":
    main()
