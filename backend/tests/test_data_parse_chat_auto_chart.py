import time

from backend.services.data_parse_session import create_session
from backend.services import data_parse_chat


def _make_fake_pipeline_result():
    """
    构造一份模拟的经营 Excel 解析结果，用于本地单元测试：
    - sheet 名为 「经营数据」
    - 列包含 「月份」「净利润」「营业收入」
    - 行为简单的时间序列数据
    """
    tables = {
        "经营数据": {
            "headers": ["月份", "净利润", "营业收入"],
            "rows": [
                ["2024-01", 100, 1000],
                ["2024-02", 200, 1200],
                ["2024-03", 150, 1100],
            ],
        }
    }
    table_schemas = [
        {
            "sheet_name": "经营数据",
            "headers": ["月份", "净利润", "营业收入"],
            "row_count": 3,
        }
    ]
    # 简化版画像：标记「月份」为时间列，「净利润」「营业收入」为指标列
    column_profiles = {
        "经营数据": [
            {
                "name": "月份",
                "type": "string",
                "null_ratio": 0.0,
                "distinct_count": 3,
                "is_time": True,
                "is_dimension": False,
                "is_metric": False,
            },
            {
                "name": "净利润",
                "type": "number",
                "null_ratio": 0.0,
                "distinct_count": 3,
                "is_time": False,
                "is_dimension": False,
                "is_metric": True,
            },
            {
                "name": "营业收入",
                "type": "number",
                "null_ratio": 0.0,
                "distinct_count": 3,
                "is_time": False,
                "is_dimension": False,
                "is_metric": True,
            },
        ]
    }
    # 聚合在当前 auto_generate_chart 逻辑中不再依赖，这里给一个空壳即可
    aggregations: dict = {}
    auto_dashboards: list = []
    return {
        "tables": tables,
        "table_schemas": table_schemas,
        "column_profiles": column_profiles,
        "aggregations": aggregations,
        "auto_dashboards": auto_dashboards,
        "kanban_config": auto_dashboards,
        "created_at": time.time(),
    }


def test_auto_chart_with_profit_trend():
    """
    模拟一份包含「月份」「净利润」「营业收入」的表，
    调用 chat(\"画一个利润趋势图\")，应当直接走后端 auto_generate_chart，
    返回可用的 chart_spec。
    """
    pipeline_result = _make_fake_pipeline_result()
    session_id = create_session(pipeline_result)

    res = data_parse_chat.chat(session_id, "画一个利润趋势图")

    assert isinstance(res, dict)
    # 不应该再返回「会话不存在/尚未上传」这类提示
    assert "利润趋势图" in res["reply"] or "趋势图" in res["reply"]

    chart_spec = res.get("chart_spec")
    assert isinstance(chart_spec, dict)
    assert chart_spec.get("xAxis", {}).get("data"), "xAxis.data 应当有时间标签"
    assert chart_spec.get("series"), "series 不应为空"

