"""
经营数据：数据来源于后台上传的 Excel，概览接口返回固定结构的 JSON 供展示页使用。

设计思路（与看板等模块一致）：
- 先定「标准结构」：GET /api/business/overview 的响应形状固定（stats、profitTrend、flowCompare、
  profitCompare），见 docs/api-contract.md「经营数据标准结构」。前端与 ECharts 只依赖该结构。
- 解析层只做「数据源 → 标准结构」的映射：本模块当前数据源为 uploads/business.xlsx，_parse_excel
  按 api-contract 中的「Excel 映射规则」将单张表区块内容填到上述四块；若日后改为 DB 或多表 Excel，
  仅调整映射逻辑即可，标准结构不变。
- 映射规则可扩展：Excel 表格式变化时，在文档中更新映射规则并在此处实现，不改变 overview 的 JSON 字段。
"""
import logging
from pathlib import Path

from fastapi import APIRouter, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse

from backend.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)

BUSINESS_EXCEL_NAME = "business.xlsx"


def _excel_path() -> Path:
    return Path(settings.upload_dir) / BUSINESS_EXCEL_NAME


def _cell(row: tuple, i: int):
    """取行第 i 列（0-based），转为 str 并 strip；空为 None 或空串则返回 ''。"""
    if row is None or i >= len(row):
        return ""
    v = row[i]
    return "" if v is None else str(v).strip()


def _num(row: tuple, i: int) -> float:
    if row is None or i >= len(row):
        return 0.0
    v = row[i]
    if v is None:
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _parse_excel(path: Path) -> dict:
    """
    将 Excel 映射为经营数据标准结构（stats / profitTrend / flowCompare / profitCompare）。
    映射规则见 docs/api-contract.md「Excel → 标准结构的映射规则」；当前实现为单张表区块格式。
    若文件不存在或解析异常，返回 _default_overview()，保证响应形状始终符合契约。
    """
    try:
        import openpyxl
    except ImportError:
        logger.warning("openpyxl 未安装，无法解析 Excel")
        return _default_overview()

    if not path.exists():
        logger.warning("经营数据 Excel 不存在: %s（当前 UPLOAD_DIR 解析为: %s）", path, path.parent)
        return _default_overview()

    try:
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    except Exception as e:
        logger.warning("解析 Excel 失败（文件可能损坏或格式不符）: %s", e)
        return _default_overview()

    # 标准结构（与 api-contract 一致），以下只填充各字段，不增删 key
    result = {
        "stats": [
            {"title": "流水", "value": "—", "desc": "万元", "completionRatio": "—"},
            {"title": "利润", "value": "—", "desc": "万元", "lastYearValue": "—", "changePercent": "—"},
            {"title": "资金", "value": "—", "desc": "万元", "overseas": "—", "overseasRatio": "—"},
        ],
        "profitTrend": {"labels": [], "currentYear": [], "previousYear": []},
        "flowCompare": {"labels": [], "actual": [], "target": []},
        "profitCompare": {"labels": [], "currentYear": [], "lastYear": []},
    }

    if not wb.worksheets:
        wb.close()
        return result

    ws = wb.worksheets[0]
    rows = list(ws.iter_rows(min_row=1, max_row=60, max_col=14, values_only=True))
    wb.close()

    # 列 B=index 1, 列 C=index 2, ...
    # 区块1：C 列为「流水」「净利润」「资金」，下一行起 B=子项、C=值
    for i, row in enumerate(rows):
        c_val = _cell(row, 2)
        b_val = _cell(row, 1)
        if c_val == "流水":
            for j in range(i + 1, min(i + 6, len(rows))):
                r = rows[j]
                b = _cell(r, 1)
                if b == "本年累计":
                    v = _cell(r, 2) or "—"
                    if r[2] is not None and not isinstance(r[2], str):
                        v = str(r[2])
                    result["stats"][0]["value"] = v
                    result["stats"][0]["desc"] = _cell(r, 3) or "万元"  # D 列单位
                elif b == "完成比例":
                    ratio_val = _cell(r, 2) or "—"
                    if r[2] is not None and not isinstance(r[2], str):
                        try:
                            n = float(r[2])
                            if 0 <= n <= 1 and n != 0:
                                ratio_val = str(round(n * 100, 1)).rstrip(".0") or "0"
                            else:
                                ratio_val = str(r[2])
                        except (TypeError, ValueError):
                            ratio_val = str(r[2])
                    result["stats"][0]["completionRatio"] = ratio_val
        elif c_val == "净利润":
            for j in range(i + 1, min(i + 6, len(rows))):
                r = rows[j]
                b = _cell(r, 1)
                if b == "本年累计":
                    v = _cell(r, 2) or "—"
                    if r[2] is not None and not isinstance(r[2], str):
                        v = str(r[2])
                    result["stats"][1]["value"] = v
                    result["stats"][1]["desc"] = _cell(r, 3) or "万元"  # D 列单位
                elif b == "去年同期":
                    v = _cell(r, 2) or "—"
                    if r[2] is not None and not isinstance(r[2], str):
                        v = str(r[2])
                    result["stats"][1]["lastYearValue"] = v
                elif b == "变动百分比":
                    pct = _cell(r, 2) or "—"
                    if r[2] is not None and not isinstance(r[2], str):
                        try:
                            n = float(r[2])
                            if -1 <= n <= 1 and n != 0:
                                pct = str(round(n * 100, 1)).rstrip(".0") or "0"
                            else:
                                pct = str(r[2])
                        except (TypeError, ValueError):
                            pct = str(r[2])
                    result["stats"][1]["changePercent"] = pct
        elif c_val == "资金":
            for j in range(i + 1, min(i + 6, len(rows))):
                r = rows[j]
                b = _cell(r, 1)
                if b == "总额":
                    v = _cell(r, 2) or "—"
                    if r[2] is not None and not isinstance(r[2], str):
                        v = str(r[2])
                    result["stats"][2]["value"] = v
                    result["stats"][2]["desc"] = _cell(r, 3) or "万元"  # D 列单位
                elif b == "海外":
                    v = _cell(r, 2) or "—"
                    if r[2] is not None and not isinstance(r[2], str):
                        v = str(r[2])
                    result["stats"][2]["overseas"] = v
                elif b == "海外占比":
                    ratio_val = _cell(r, 2) or "—"
                    if r[2] is not None and not isinstance(r[2], str):
                        try:
                            n = float(r[2])
                            if 0 <= n <= 1 and n != 0:
                                ratio_val = str(round(n * 100, 1)).rstrip(".0") or "0"
                            else:
                                ratio_val = str(r[2])
                        except (TypeError, ValueError):
                            ratio_val = str(r[2])
                    result["stats"][2]["overseasRatio"] = ratio_val

    # 区块2：B=净利润 且 C/D/E/… 为 1月～12月，下一行 B=本年，再下一行 B=去年（最多12个月）
    for i, row in enumerate(rows):
        if _cell(row, 1) != "净利润":
            continue
        labels = []
        for col in range(2, 14):
            s = _cell(row, col)
            if s and ("月" in s or s.isdigit()):
                labels.append(s)
        if not labels:
            continue
        cur_y, prev_y = [], []
        for j in range(i + 1, min(i + 4, len(rows))):
            r = rows[j]
            if _cell(r, 1) == "本年":
                cur_y = [_num(r, c) for c in range(2, 2 + len(labels))]
                cur_y = (cur_y + [0] * len(labels))[:len(labels)]
            elif _cell(r, 1) == "去年":
                prev_y = [_num(r, c) for c in range(2, 2 + len(labels))]
                prev_y = (prev_y + [0] * len(labels))[:len(labels)]
        if labels:
            result["profitTrend"]["labels"] = labels
            result["profitTrend"]["currentYear"] = cur_y if cur_y else [0] * len(labels)
            result["profitTrend"]["previousYear"] = prev_y if prev_y else [0] * len(labels)
        break

    # 区块3：B=流水 且 C～L 为项目名（最多10项，与利润区块一致），下一行 B=本年累计，再下一行 B=目标
    for i, row in enumerate(rows):
        if _cell(row, 1) != "流水":
            continue
        projs = []
        for col in range(2, 12):
            s = _cell(row, col)
            if s and s != "本年累计":
                projs.append(s)
        if not projs:
            continue
        actual, target = [], []
        for j in range(i + 1, min(i + 5, len(rows))):
            r = rows[j]
            if _cell(r, 1) == "本年累计":
                actual = [_num(r, c) for c in range(2, 2 + len(projs))]
                actual = (actual + [0] * len(projs))[:len(projs)]
            elif _cell(r, 1) == "目标":
                target = [_num(r, c) for c in range(2, 2 + len(projs))]
                target = (target + [0] * len(projs))[:len(projs)]
        if projs:
            result["flowCompare"]["labels"] = projs
            result["flowCompare"]["actual"] = actual if actual else [0] * len(projs)
            result["flowCompare"]["target"] = target if target else [0] * len(projs)
        break

    # 区块4：B=利润 且 C～L 为项目名（最多10项），下一行 B=本年累计，再下一行 B=去年/去年同期
    for i, row in enumerate(rows):
        if _cell(row, 1) != "利润":
            continue
        projs = []
        for col in range(2, 12):
            s = _cell(row, col)
            if s:
                projs.append(s)
        if not projs:
            continue
        cur_y, last_y = [], []
        for j in range(i + 1, min(i + 5, len(rows))):
            r = rows[j]
            b = _cell(r, 1)
            if b in ("本年累计", "本年"):
                cur_y = [_num(r, c) for c in range(2, 2 + len(projs))]
                cur_y = (cur_y + [0] * len(projs))[:len(projs)]
            elif b in ("去年", "去年同期"):
                last_y = [_num(r, c) for c in range(2, 2 + len(projs))]
                last_y = (last_y + [0] * len(projs))[:len(projs)]
        if projs:
            result["profitCompare"]["labels"] = projs
            result["profitCompare"]["currentYear"] = cur_y if cur_y else [0] * len(projs)
            result["profitCompare"]["lastYear"] = last_y if last_y else [0] * len(projs)
        break

    return result


def _default_overview() -> dict:
    """无数据或解析失败时返回的空结构，与标准结构契约一致，便于前端安全渲染。"""
    return {
        "stats": [
            {"title": "流水", "value": "—", "desc": "万元", "completionRatio": "—"},
            {"title": "利润", "value": "—", "desc": "万元", "lastYearValue": "—", "changePercent": "—"},
            {"title": "资金", "value": "—", "desc": "万元", "overseas": "—", "overseasRatio": "—"},
        ],
        "profitTrend": {"labels": [], "currentYear": [], "previousYear": []},
        "flowCompare": {"labels": [], "actual": [], "target": []},
        "profitCompare": {"labels": [], "currentYear": [], "lastYear": []},
    }


@router.post("/upload")
async def business_upload(file: UploadFile = File(...)):
    """上传经营数据 Excel，覆盖已有 business.xlsx。仅内网使用，生产环境应加鉴权。"""
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="请上传 .xlsx 或 .xls 文件")
    path = _excel_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    content = await file.read()
    path.write_bytes(content)
    return {"ok": True, "message": "已保存，经营数据页将从此文件读取。"}


@router.get("/overview")
def business_overview():
    """
    经营数据概览：从已上传的 Excel（uploads/business.xlsx）解析，
    返回流水/利润/资金三个指标及三张图表数据。若无文件或解析失败则返回默认空值。
    """
    data = _parse_excel(_excel_path())
    return JSONResponse(content=data, headers={"Cache-Control": "no-store, no-cache"})


@router.get("/summary")
def business_summary():
    """
    经营数据摘要，供首页/其他入口展示。
    数据来源为同一份 Excel；与 /overview 一致，返回简要指标。
    """
    data = _parse_excel(_excel_path())
    body = {
        "updatedAt": "",  # 可选：从文件 mtime 或 Excel 内单元格读取
        "indicators": [{"name": s["title"], "value": s["value"], "unit": s["desc"]} for s in data["stats"]],
        "chart": {"labels": data["profitTrend"]["labels"], "series": [{"name": "本年", "data": data["profitTrend"]["currentYear"]}]},
    }
    return JSONResponse(content=body, headers={"Cache-Control": "no-store, no-cache"})
