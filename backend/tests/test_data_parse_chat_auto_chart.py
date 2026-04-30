import time
from unittest.mock import patch

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


def test_session_table_bootstrap_lists_sheets():
    """服务端快照须包含工作表名，供 LLM 在未调 read_metrics 前也能识别有表。"""
    pipeline_result = _make_fake_pipeline_result()
    session_id = create_session(pipeline_result)
    boot = data_parse_chat._session_table_bootstrap(session_id)
    assert "经营数据" in boot
    assert "当前会话表结构快照" in boot
    assert "禁止" in boot or "未绑定" in boot


def test_sheet_usage_risk_is_deterministic_and_not_claim_no_tables():
    """
    当用户问「列出各工作表用途与主要风险」时，应走后端确定性答复，
    不允许出现“未绑定/未检测到有效表格”类误导。
    """
    pipeline_result = _make_fake_pipeline_result()
    # 制造一堆空列名，模拟用户 business.xlsx 这种“列很多但大多空”的情况
    pipeline_result["tables"]["经营数据"]["headers"] = ["月份", "净利润", "营业收入"] + [""] * 20
    pipeline_result["table_schemas"][0]["headers"] = pipeline_result["tables"]["经营数据"]["headers"]
    session_id = create_session(pipeline_result)
    res = data_parse_chat.chat(session_id, "请根据已上传的表格，用要点列出各工作表用途与主要风险（勿编造具体数值）。")
    assert isinstance(res, dict)
    txt = res.get("reply") or ""
    assert "工作表「经营数据」" in txt
    assert "未检测到有效表格" not in txt
    assert "会话ID失效" not in txt


def test_risk_only_prompt_is_also_deterministic():
    """
    仅问“主要风险”时也应走确定性分支，避免模型误报 session 不存在。
    """
    pipeline_result = _make_fake_pipeline_result()
    pipeline_result["tables"]["经营数据"]["headers"] = ["月份", "净利润", "营业收入"] + [""] * 5
    pipeline_result["table_schemas"][0]["headers"] = pipeline_result["tables"]["经营数据"]["headers"]
    session_id = create_session(pipeline_result)
    res = data_parse_chat.chat(session_id, "分析经营的主要风险（勿编造具体表述）。")
    txt = res.get("reply") or ""
    assert "session 不存在" not in txt
    assert "工作表「经营数据」" in txt
    assert "主要风险" in txt


def test_auto_chart_fallback_works_without_column_profiles():
    pipeline_result = _make_fake_pipeline_result()
    pipeline_result["column_profiles"] = {}
    session_id = create_session(pipeline_result)
    res = data_parse_chat.chat(session_id, "生成图表")
    assert isinstance(res.get("chart_spec"), dict)
    assert "自动生成" in (res.get("reply") or "")


def test_llm_session_missing_hallucination_is_rewritten():
    pipeline_result = _make_fake_pipeline_result()
    session_id = create_session(pipeline_result)

    def _fake_chat(_messages, tools=None):
        return {"message": {"content": "当前会话 session 不存在或已过期，无法获取表格数据进行分析。", "tool_calls": []}}

    with patch("backend.services.data_parse_chat._call_ollama_chat", side_effect=_fake_chat):
        res = data_parse_chat.chat(session_id, "请分析经营主要风险")
    txt = res.get("reply") or ""
    assert "session 不存在" not in txt
    assert "当前会话有效" in txt or "工作表" in txt


def test_metric_lookup_no_match_does_not_claim_session_missing():
    pipeline_result = _make_fake_pipeline_result()
    session_id = create_session(pipeline_result)
    res = data_parse_chat.chat(session_id, "破天一剑的流水如何")
    txt = res.get("reply") or ""
    assert "当前会话有效" in txt
    assert "session 不存在" not in txt


def test_metric_lookup_supports_transposed_table():
    pipeline_result = {
        "tables": {
            "Sheet1": {
                "headers": ["流水", "破天一剑"],
                "rows": [["本年累计", 10], ["目标", 100]],
            }
        },
        "table_schemas": [{"sheet_name": "Sheet1", "headers": ["流水", "破天一剑"], "row_count": 2, "is_main_sheet": True}],
        "column_profiles": {},
        "aggregations": {},
        "auto_dashboards": [],
        "kanban_config": [],
        "validation_summary": {},
    }
    session_id = create_session(pipeline_result)
    res = data_parse_chat.chat(session_id, "破天一剑的流水如何")
    txt = res.get("reply") or ""
    assert "10.00" in txt
    assert "完成率" in txt

