"""
生成本地开发用经营数据 Excel → uploads/business.xlsx
格式见 specs/api/api-contract.md「Excel → 标准结构的映射规则」。

用法（项目根目录）：
  .\\.venv\\Scripts\\python.exe scripts\\seed_business_dashboard_xlsx.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import openpyxl
except ImportError as e:
    raise SystemExit("需要 openpyxl：pip install openpyxl") from e

from backend.config import settings
from backend.routers.business import BUSINESS_EXCEL_NAME, _parse_excel


def _write_sheet(ws) -> None:
    """按 business._parse_excel 约定写入单表区块（B=标签/表头，C=数值或区块标题，D=单位）。"""
    rows: list[list] = []

    # 区块 1：指标（标题在 C 列）
    rows.append(["", "", "流水", ""])
    rows.append(["", "本年累计", 12580, "万元"])
    rows.append(["", "目标", 15000, "万元"])
    rows.append(["", "完成比例", 83.9, ""])
    rows.append([])
    rows.append(["", "", "净利润", ""])
    rows.append(["", "本年累计", 3260, "万元"])
    rows.append(["", "去年同期", 2850, "万元"])
    rows.append(["", "变动百分比", 14.4, ""])
    rows.append([])
    rows.append(["", "", "资金", ""])
    rows.append(["", "总额", 8120, "万元"])
    rows.append(["", "海外", 1180, "万元"])
    rows.append(["", "海外占比", 0.145, ""])
    rows.append([])

    # 区块 2：利润趋势（表头在 B=净利润，月份从 C 起）
    rows.append(["", "净利润", "1月", "2月", "3月", "4月", "5月", "6月"])
    rows.append(["", "本年", 210, 245, 268, 290, 312, 335])
    rows.append(["", "去年", 198, 220, 235, 250, 265, 280])
    rows.append([])

    # 区块 3：流水按项目（表头在 B=流水）
    rows.append(["", "流水", "破天一剑", "丝路传说", "其他"])
    rows.append(["", "本年累计", 5200, 4800, 2580])
    rows.append(["", "目标", 6000, 5500, 3500])
    rows.append([])

    # 区块 4：利润按项目（表头在 B=利润）
    rows.append(["", "利润", "破天一剑", "丝路传说", "其他"])
    rows.append(["", "本年累计", 1420, 1280, 560])
    rows.append(["", "去年", 1250, 1180, 520])

    for r in rows:
        ws.append(r)


def main() -> int:
    out_dir = Path(settings.upload_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / BUSINESS_EXCEL_NAME

    if out_path.exists() and out_path.stat().st_size > 0:
        print(f"[ABORT] 已存在 {out_path}（{out_path.stat().st_size} 字节），为防覆盖真实数据已停止。")
        print("若确为开发样例，请先手动备份/移走该文件后再运行。")
        return 1

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    _write_sheet(ws)
    wb.save(out_path)

    parsed = _parse_excel(out_path)
    pt = parsed.get("profitTrend") or {}
    fc = parsed.get("flowCompare") or {}
    print(f"[OK] 已写入 {out_path}")
    print(f"     流水 stats[0].value = {parsed['stats'][0].get('value')}")
    print(f"     利润趋势月份数 = {len(pt.get('labels') or [])}")
    print(f"     流水项目数 = {len(fc.get('labels') or [])}")
    print("刷新经营数据页（/）即可看到图表。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
