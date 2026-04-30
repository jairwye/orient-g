"""内存生成最小 .xlsx，走 run_pipeline，覆盖 v1.2.2.f 数据解析方案中的解析链路基线。"""

import io

import pytest

from backend.services.data_parse import run_pipeline


def _minimal_xlsx_bytes() -> bytes:
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "经营数据"
    ws.append(["月份", "净利润", "营业收入"])
    ws.append(["2024-01", 100, 1000])
    ws.append(["2024-02", 200, 1200])
    buf = io.BytesIO()
    wb.save(buf)
    data = buf.getvalue()
    assert len(data) >= 100, "validate_upload 要求文件不小于 100 字节"
    return data


def test_run_pipeline_parses_in_memory_xlsx():
    content = _minimal_xlsx_bytes()
    result = run_pipeline(content, "unit_test_minimal.xlsx")

    assert isinstance(result, dict)
    tables = result.get("tables") or {}
    assert isinstance(tables, dict)
    assert len(tables) >= 1

    first_key = next(iter(tables))
    first = tables[first_key]
    assert isinstance(first, dict)
    assert "headers" in first and "rows" in first
    assert len(first["headers"]) >= 1
    assert len(first["rows"]) >= 1

    schemas = result.get("table_schemas") or []
    assert isinstance(schemas, list)
    assert len(schemas) >= 1

    profiles = result.get("column_profiles") or {}
    assert isinstance(profiles, dict)

    assert "validation_summary" in result


def test_validate_upload_rejects_tiny_file():
    from backend.services.data_parse import validate_upload

    with pytest.raises(ValueError, match="过小"):
        validate_upload(b"x" * 50, "bad.xlsx")


def test_parse_trims_trailing_empty_columns_and_normalizes_headers():
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    # 模拟“非严格表格”：表头中有空列名、末尾大量空列
    ws.append(["月份", "", "流水", "", ""])
    ws.append(["2024-01", "", 1000, "", ""])
    ws.append(["2024-02", "", 1200, "", ""])
    buf = io.BytesIO()
    wb.save(buf)
    content = buf.getvalue()
    result = run_pipeline(content, "non_strict.xlsx")
    tables = result.get("tables") or {}
    t = tables.get("Sheet1") or {}
    headers = t.get("headers") or []
    # 空列名应补齐为“列N”，且不会被固定扩成 MAX_COLS=200
    assert len(headers) <= 5
    assert headers[0] == "月份"
    assert headers[1].startswith("列")
