from backend.services.data_parse_output_validate import append_output_shape_audit


def test_audit_appends_when_json_missing_keys():
    raw = '{"conclusion":"ok"}'
    out = append_output_shape_audit(raw, prompt_addon="prompt.data_parse.output_shape.v1")
    assert "缺少字段" in out
    assert "risks" in out or "suggestions" in out


def test_audit_noop_when_not_json():
    out = append_output_shape_audit("这是普通分析结论。", prompt_addon="prompt.data_parse.output_shape.v1")
    assert out == "这是普通分析结论。"


def test_audit_noop_without_output_shape_hint():
    bad = '{"foo":1}'
    out = append_output_shape_audit(bad, prompt_addon="仅摘要")
    assert out == bad
