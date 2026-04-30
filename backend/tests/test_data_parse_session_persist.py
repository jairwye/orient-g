from backend.services import data_parse_session as dps


def test_session_can_be_loaded_from_disk_when_memory_miss():
    pipeline_result = {
        "tables": {"经营数据": {"headers": ["月份", "净利润"], "rows": [["2024-01", 100]]}},
        "table_schemas": [{"sheet_name": "经营数据", "headers": ["月份", "净利润"], "row_count": 1}],
        "column_profiles": {},
        "aggregations": {},
        "auto_dashboards": [],
        "kanban_config": [],
        "validation_summary": {},
    }
    sid = dps.create_session(pipeline_result)
    # 模拟“另一个进程”场景：当前内存缓存不存在该会话
    dps._sessions.pop(sid, None)  # type: ignore[attr-defined]
    s = dps.get_session(sid)
    assert isinstance(s, dict)
    tables = s.get("tables") or {}
    assert "经营数据" in tables
