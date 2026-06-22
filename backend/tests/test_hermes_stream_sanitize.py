"""Hermes 流式正文与推理分流（TDD）。"""

from __future__ import annotations

from backend.services.hermes_stream_sanitize import (
    classify_hermes_stream_chunk,
    enforce_breakdown_compare_reply,
    extract_user_facing_reply,
    finalize_agent_reply,
    looks_like_planning,
    normalize_reply_markdown,
    reply_has_unsupported_estimates,
    reply_has_verifiable_breakdown_table,
    sanitize_hermes_accumulated_reply,
)


def test_classify_planning_as_thinking():
    chunk = "用户要求出具销售费用对比。步骤：先调用 orientg_kb_ask。"
    assert classify_hermes_stream_chunk(chunk) == "thinking"
    assert looks_like_planning(chunk)


def test_classify_report_opening_as_delta_not_根据():
    chunk = "根据检索到的可比公司E2024年与2025年财务报告数据，以下是"
    assert classify_hermes_stream_chunk(chunk) == "delta"
    assert not looks_like_planning(chunk)


def test_classify_code_execution_as_thinking():
    chunk = 'import urllib.request\nlogin_url = "http://127.0.0.1:8000/api/auth/login"'
    assert classify_hermes_stream_chunk(chunk) == "thinking"


def test_classify_report_table_as_delta():
    chunk = "| 项目 | 2025年 | 2024年 |\n| 销售费用 | 8,851,536.62 | 17,783,841.20 |"
    assert classify_hermes_stream_chunk(chunk) == "delta"


def test_normalize_glued_table_and_conclusion():
    raw = (
        "基于母公司数据的销售费用对比（唯一可信数据）|项目 |2025年 |2024年 |"
        "变动额 |变动幅度 || :--- | :--- | :--- | :--- | :--- |"
        " | 销售费用 |8,851,536.62 |17,783,841.20 | -8,932,304.58 | -50.23% |"
        "结论：1. 数据缺失"
    )
    out = normalize_reply_markdown(raw)
    assert "\n\n|" in out or out.count("\n|") >= 2
    assert "结论" in out
    assert "8,851,536.62" in out
    raw = (
        "检索到的数据，以下是关于销售费用的对比分析报告。###可比E2025-2024年销售费用对比分析报告"
        "####1.核心数据概览|项目 |2025年 |2024年 || :--- | :--- | :--- | :--- | :--- |"
        " | 销售费用 | 13,722,360.23 | 25,081,092.51 |"
    )
    out = normalize_reply_markdown(raw)
    assert "### 可比E" in out or "###可比E" in out
    assert "\n|" in out or "|\n|" in out


def test_extract_user_facing_reply_strips_planning_prefix():
    raw = (
        "用户要求出具报告。步骤：检索。\n"
        "根据 orientg-debugging，知识库中不包含销售费用明细。\n\n"
        "### 可比E销售费用对比\n\n"
        "| 项目 | 2025年 | 2024年 |\n"
        "| 销售费用 | 8,851,536.62 | 17,783,841.20 |"
    )
    out = extract_user_facing_reply(raw)
    assert out.startswith("###")
    assert "8,851,536.62" in out
    assert "用户要求" not in out


def test_enforce_strips_estimate_breakdown_section():
    q = "可比E25、24两年销售费用明细的对比分析报告"
    raw = (
        "### 可比E对比\n\n| 项目 | 2025 | 2024 |\n| :--- | :--- | :--- |\n| 销售费用 | 1 | 2 |\n\n"
        "####2.费用变动分析\n\n* 人员薪酬减少约 500-600万元。\n\n3.结论\n\n收尾。"
    )
    assert reply_has_unsupported_estimates(raw)
    out = enforce_breakdown_compare_reply(raw, user_query=q)
    assert "500-600" not in out
    assert "费用明细说明" in out
    assert "收尾" in out or "结论" in out


def test_normalize_tsv_table_to_markdown():
    raw = (
        "结论：2025年销售费用合计13,722,360.23元。\t项目\t2025年\t2024年\t差额\t同比变动\n"
        "销售费用合计\t13,722,360.23\t25,081,092.51\t-11,358,732.28\t-45.29%\n"
        "职工薪酬\t10,802,366.11\t23,295,127.31\t-12,492,761.20\t-53.63%"
    )
    out = normalize_reply_markdown(raw)
    assert "| 项目 | 2025年 |" in out
    assert "| 销售费用合计 |" in out
    assert "结论：2025年销售费用合计" in out


def test_strip_orchestration_preamble_before_report_title():
    from backend.services.hermes_stream_sanitize import finalize_agent_reply, strip_hermes_orchestration_preamble

    raw = (
        "先根据已有证据把报告写出来。\n\n"
        "这个 skill不相关，不需要加载。预检索证据已经非常充分，`orientg_kb_ask`。\n\n"
        "让我直接输出：---#可比公司E2025年与2024年销售费用对比分析报告\n\n"
        "## 结论2025年销售费用合计13,722,360.23元。\n"
    )
    out = strip_hermes_orchestration_preamble(raw)
    assert out.startswith("#可比公司E") or out.startswith("可比公司E")
    assert "skill不相关" not in out
    assert "orientg_kb_ask" not in out


def test_strip_english_evidence_pack_preamble():
    from backend.services.hermes_stream_sanitize import finalize_agent_reply, strip_hermes_orchestration_preamble

    raw = (
        "Based on the Evidence Pack provided, I have all the necessary data to write the report. "
        "No additional API calls are needed."
        "可比公司E2025年营业收入对比分析报告结论：2025年营业收入为100,148,026.24元。"
    )
    out = strip_hermes_orchestration_preamble(raw)
    assert out.startswith("可比公司E")
    assert "Evidence Pack" not in out[:40]
    fin = finalize_agent_reply(raw, user_query="可比E2025年与2024年营业收入对比")
    assert "100,148,026.24" in fin
    assert not fin.lower().startswith("based on")
    q = "可比E25、24两年销售费用明细的对比分析报告"
    fin = finalize_agent_reply(raw, user_query=q)
    assert fin.startswith("#") or fin.startswith("可比E") or "结论" in fin[:40]
    assert "skill" not in fin[:200].lower() or "可比E" in fin[:80]


def test_normalize_user_paste_glued_report():
    """浏览器实测常见：标题/表/小节挤一行、导语重复。"""
    raw = (
        "根据检索到的财务附注数据，以下是可比E2025年与2024年销售费用的明细对比分析报告。\n"
        "可比E2025-2024年销售费用明细对比分析报告\n"
        "1.费用总额与结构概览2025年，可比E销售费用总额大幅缩减，较2024年下降了 45.29%。"
        "这一降幅远超同期营业收入的降幅（-27.71%），显示出公司在市场端采取了激进的收缩策略。|项目 |2025年 (元) |2024年 (元) |变动额 (元) |变动幅度 |\n"
        "| :--- | :--- | :--- | :--- | :--- |\n"
        "| 销售费用合计 |13,722,360.23 |25,081,092.51 | -11,358,732.28 | -45.29% |\n"
        "| 销售费用率 | 13.70% | 18.10% | -4.40% | — |#### 2.核心明细项目变动分析"
        "销售费用的下降主要由人员相关费用和市场投入的削减驱动。"
    )
    out = finalize_agent_reply(raw, user_query="可比E25、24两年销售费用明细的对比分析报告", tier2_native=True)
    assert "根据检索到的财务附注数据" not in out[:80] or "## 可比E" in out
    assert "## 可比E" in out or "#### 1." in out
    assert "| 销售费用合计 |" in out
    assert "13,722,360.23" in out
    assert "13.70%" in out
    assert "| — | ####" not in out
    assert "#### 2." in out
    assert "\n\n#### 2." in out or out.index("#### 2.") > out.index("13.70%")


def test_enforce_keeps_table_strips_yue_wan_in_prose():
    """补检索 synth：有附注表时不得插入「无分项」占位，须去掉正文「约 xx 万」。"""
    synth = (
        "可比公司E2025年与2024年研发费用明细对比分析报告\n"
        "1. 结论\n\n"
        "2025年研发费用合计 123,448,492.22元，较2024年 176,499,977.92元 减少 53,051,485.70元。\n"
        "2. 费用明细说明\n\n"
        "（略）\n"
        "3. 研发费用明细对比\n"
        "| 项目 | 2025年（本期） | 2024年（上期） | 变动额（元） | 变动幅度 |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| 工资薪金 | 96,128,672.18 | 131,830,431.38 | -35,701,759.20 | -27.08% |\n"
        "| 合计 | 123,448,492.22 | 176,499,977.92 | -53,051,485.70 | -30.06% |\n"
        "4. 变动原因说明\n\n"
        "工资薪金减少约3570万元，员工保险减少约1466万元，两者合计减少约5036万元。\n"
    )
    out = finalize_agent_reply(
        synth,
        user_query="出一份可比E25、24两年研发费用明细的对比分析报告",
    )
    assert "证据中未提供可核查的分项金额" not in out
    assert "96,128,672.18" in out
    assert "约3570万元" not in out
    assert "约1466万元" not in out
    assert reply_has_verifiable_breakdown_table(out)


def test_normalize_rd_glued_conclusion_pipe_table_and_shuoming():
    """标准轮实测：结论与 |项目| 表、表尾与「说明」粘连。"""
    raw = (
        "结论：2025年研发费用合计120,565,207.54元，较2024年的172,697,867.39元减少52,132,659.85元，降幅30.18%；"
        "分项中职工薪酬大幅减少，折旧及摊销费用增加。|项目 |2025年 |2024年 |差额 |同比 |\n"
        "|---|---|---|---|---|\n"
        "|职工薪酬 |70,863,000.00 |122,568,000.00 | -51,705,000.00 | -42.19% |\n"
        "|合计 |120,565,207.54 |172,697,867.39 | -52,132,659.85 | -30.18% |说明：1. 变动原因：人员减少。"
        "2. 分项明细：职工薪酬降幅42.19%。"
    )
    out = finalize_agent_reply(raw, user_query="可比E25、24两年研发费用明细的对比分析报告")
    assert "增加。|项目" not in out
    assert "\n\n|" in out
    assert "|职工薪酬 |" in out or "| 职工薪酬 |" in out
    assert "### 说明" in out
    assert "120,565,207.54" in out
    assert "|合计 |120,565,207.54" in out
    assert "\n\n### 说明" in out or out.rstrip().endswith("42.19%。") or "人员减少" in out


def test_pick_best_hermes_runs_raw_prefers_structured_final():
    from backend.services.hermes_stream_sanitize import pick_best_hermes_runs_raw

    acc = "结论：2025年销售费用合计13,722,360.23元\t项目\t2025年"
    fin = (
        "### 可比E 2025-2024 年销售费用对比\n\n"
        "| 项目 | 2025年 | 2024年 |\n| --- | --- | --- |\n"
        "| 销售费用合计 | 13,722,360.23 | 25,081,092.51 |"
    )
    assert pick_best_hermes_runs_raw(acc, fin) == fin


def test_normalize_glued_conclusion_tsv_to_markdown_table():
    raw = (
        "结论：2025年销售费用合计13,722,360.23元，较2024年的25,081,092.51元减少11,358,732.28元，降幅45.29%。"
        "\t项目\t2025年\t2024年\t差额\t同比变动\n"
        "职工薪酬\t10,802,360.11\t23,295,127.31\t-12,492,761.20\t-53.63%\n"
        "合计\t13,722,360.23\t25,081,092.51\t-11,358,732.28\t-45.29%"
    )
    out = normalize_reply_markdown(raw)
    assert "## 结论" in out or "结论" in out
    assert "| 项目 | 2025年 |" in out
    assert "| 职工薪酬 |" in out
    assert "\t" not in out or out.count("\t") < 2


def test_strip_inline_source_markers_from_reply():
    from backend.services.hermes_stream_sanitize import finalize_agent_reply, strip_inline_source_markers

    raw = (
        "变动原因：主要系人员减少。"
        " [doc_chunk ud_0401544fb6f7425092db1d9f7a970917#ud_0401544fb6f7425092db1d9f7a970917_s0001]"
        " [evidence_pack 31 、销售费用]"
    )
    assert "[doc_chunk" not in strip_inline_source_markers(raw)
    assert "[evidence_pack" not in strip_inline_source_markers(raw)
    fin = finalize_agent_reply(
        raw + "\n| 合计 | 13,722,360.23 |",
        user_query="对比分析",
        tier2_native=True,
    )
    assert "[doc_chunk" not in fin


def test_full_body_strips_python_script_before_report():
    from backend.services.hermes_stream_sanitize import HermesDraftTraceAccumulator

    acc = HermesDraftTraceAccumulator()
    acc.push("让我先搜索。\nimport json\nprint('x')\n")
    acc.push("## 可比E管理费用\n| 管理费用 | 44,933,044.34 |\n")
    body = acc.full_body()
    assert "import json" not in body
    assert "44,933,044.34" in body


def test_extract_user_facing_reply_strips_english_runs_preamble():
    from backend.services.hermes_stream_sanitize import extract_user_facing_reply

    raw = (
        "I'll start by searching the Orient-G knowledge base for R&D expense details.\n"
        "Let me use the MCP tools directly.\n"
        "Login failed. Let me check the app settings.\n"
        "## 可比公司E研发费用对比分析报告\n"
        "一、结论\n2025年研发费用 123,448,492.22 元。\n"
    )
    out = extract_user_facing_reply(raw)
    assert "I'll start" not in out
    assert "Login failed" not in out
    assert "123,448,492.22" in out


def test_resolve_hermes_effective_reply_prefers_deferred_draft():
    from backend.services.hermes_stream_sanitize import (
        HermesDraftTraceAccumulator,
        resolve_hermes_effective_reply,
    )

    acc = HermesDraftTraceAccumulator()
    acc.push("## 可比E管理费用\n| 管理费用 | 44,933,044.34 |\n")
    out = resolve_hermes_effective_reply(evt_reply="", draft_acc=acc)
    assert "44,933,044.34" in out
    assert len(out) > 20


def test_hermes_draft_accumulator_not_single_chunk_fragment():
    from backend.services.hermes_stream_sanitize import HermesDraftTraceAccumulator, format_hermes_draft_trace

    acc = HermesDraftTraceAccumulator()
    chunks = [
        "2025年度可比公司E销售费用",
        "对比分析",
        "\n### 可比E 2025-2024 销售费用对比\n\n",
        "| 项目 | 2025 | 2024 |\n| 销售费用 | 13,722,360.23 | 25,081,092.51 |",
    ]
    last = ""
    for c in chunks:
        d = acc.push(c)
        if d:
            last = d
    assert "13,722,360.23" in last
    assert last.startswith("### 可比E")
    assert format_hermes_draft_trace("市场份额") == "市场份额"


def test_format_hermes_draft_trace_prefers_report_section():
    from backend.services.hermes_stream_sanitize import format_hermes_draft_trace

    garbled = (
        "乱码片段###清52销售1核心览0年"
        "\n### 可比E 2025-2024 销售费用对比\n\n"
        "| 项目 | 2025 | 2024 |\n| 销售费用 | 13,722,360.23 | 25,081,092.51 |"
    )
    out = format_hermes_draft_trace(garbled)
    assert out.startswith("### 可比E")
    assert "13,722,360.23" in out
    assert "乱码片段" not in out[:20]


def test_strip_inline_ud_id_and_document_brackets():
    from backend.services.hermes_stream_sanitize import strip_inline_source_markers

    raw = (
        "变动原因见 ud_0401544fb6f7425092db1d9f7a970917 与 [document 可比E2025年报] "
        "及 [source: doc_chunk ud_x#ud_x_s0002]。"
    )
    out = strip_inline_source_markers(raw)
    assert "ud_0401544" not in out
    assert "[document" not in out
    assert "[source:" not in out
    assert "变动原因见" in out


def test_enforce_strips_derived_payroll_row():
    q = "出一份可比E25、24两年研发费用明细的对比分析报告"
    raw = (
        "结论：合计 120,565,207.54 元。\n\n"
        "| 项目 | 2025 | 2024 |\n| 职工薪酬 | 70,863,000.00 | 122,568,000.00 |\n\n"
        "*(注：2025年职工薪酬系根据2024年减去变动额计算得出)*\n"
    )
    out = enforce_breakdown_compare_reply(raw, user_query=q)
    assert "计算得出" not in out


def test_strip_inline_leaves_no_empty_parens():
    from backend.services.hermes_stream_sanitize import finalize_agent_reply, strip_inline_source_markers

    raw = "附注（[doc_chunk ud_abc#ud_abc_s1]）与章节（doc_id: `ud_abc`）。"
    out = strip_inline_source_markers(raw)
    assert "（）" not in out
    assert "()" not in out
    assert "附注与章节。" in out.replace(" ", "")


def test_strip_inline_empty_evidence_backticks():
    from backend.services.hermes_stream_sanitize import strip_inline_source_markers

    raw = "> 注：以上数据来源于证据 ` ` 中的“33、研发费用”表格。"
    out = strip_inline_source_markers(raw)
    assert "` `" not in out
    assert "证据" in out
    assert "33、研发费用" in out


def test_normalize_splits_glued_hr_headings():
    raw = "合计 123,448,492.22 元。---## 一、核心指标\n\n| 项目 |"
    out = normalize_reply_markdown(raw)
    assert "---##" not in out
    assert "## 一、核心指标" in out or "##一、核心指标" in out


def test_finalize_tier2_strips_unsupported_estimate_sections():
    from backend.services.hermes_stream_sanitize import finalize_agent_reply

    q = "可比E25、24两年销售费用明细的对比分析报告"
    raw = (
        "# 可比E对比\n\n| 项目 | 2025 | 2024 |\n| :--- | :--- | :--- |\n| 销售费用 | 13,722,360.23 | 25,081,092.51 |\n\n"
        "#### 2. 费用变动分析\n\n"
        "* 人员薪酬：较 2024 年减少约 500-600 万元。\n"
        "* 市场推广：减少约 300-400 万元。\n\n"
        "#### 3. 结论\n\n总额下降。\n"
    )
    out = finalize_agent_reply(raw, user_query=q, tier2_native=True)
    assert "500-600" not in out
    assert "300-400" not in out
    assert "13,722,360.23" in out
    assert "费用明细说明" in out or "无法按科目展开" in out


def test_reply_has_unsupported_speculation_detects_kenengxi():
    from backend.services.hermes_stream_sanitize import reply_has_unsupported_speculation

    assert reply_has_unsupported_speculation("* **原因**：可能系部分固定资产已提足折旧。")
    assert not reply_has_unsupported_speculation(
        "* **原因**：主要系使用权资产减少，租赁面积缩减。"
    )


def test_finalize_strips_speculation_and_evidence_pack_inline():
    from backend.services.hermes_stream_sanitize import finalize_agent_reply

    q = "出一份可比E25、24两年管理费用明细的对比分析报告"
    raw = (
        "结论：管理费用 44,933,044.34 元。\n"
        "| 管理费用 | 44,933,044.34 | 52,950,207.05 |\n"
        "4.变动原因\n"
        "* **原因**：可能系公司减少了审计、法律或咨询等外部专业服务采购。\n"
        "引用证据：数据明细：`evidence_pack 32 、管理费用`、\n"
    )
    out = finalize_agent_reply(raw, user_query=q, tier2_native=False)
    assert "可能系" not in out
    assert "evidence_pack" not in out
    assert "44,933,044.34" in out
    assert "证据未提供变动原因" in out or "仅列示金额" in out


def test_finalize_tier2_native_strips_speculation_keeps_hermes_body():
    from backend.services.hermes_stream_sanitize import finalize_agent_reply

    q = "出一份可比E25、24两年管理费用明细的对比分析报告"
    raw = (
        "## 可比E管理费用对比分析\n\n"
        "结论：2025 年管理费用较 2024 年下降 15.1%。\n"
        "| 管理费用 | 44,933,044.34 | 52,950,207.05 |\n"
        "#### 4. 变动原因\n"
        "* **原因**：可能系公司减少了审计、法律或咨询等外部专业服务采购。\n"
        "#### 5. 盈利能力影响\n"
        "管理费用率下降，有利于提升净利率。\n"
        "引用证据：`evidence_pack 32`\n"
    )
    out = finalize_agent_reply(raw, user_query=q, tier2_native=True)
    assert "可能系" not in out
    assert "evidence_pack" not in out
    assert "盈利能力影响" in out
    assert "44,933,044.34" in out
