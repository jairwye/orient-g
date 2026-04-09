"""
数据解析对话：Ollama /api/chat + 工具（read_metrics, template_render, generate_chart, generate_table）。
仅基于 session 内聚合数据，不把原始行级数据拼进 prompt。
"""
import json
import logging
import re
from pathlib import Path
from typing import Any

import httpx

from backend.config import settings
from backend.services.ollama_guard import post_json_with_guard
from backend.services.data_parse_session import (
    get_kanban_config,
    get_metrics,
    get_session,
    get_tables,
    get_table_schemas,
)

logger = logging.getLogger(__name__)

SKILLS_PATH = Path(__file__).resolve().parent.parent / "data" / "kanban_skills.json"
DEFAULT_MODEL = "qwen3:8b-q4_K_M"
MAX_TOOL_ROUNDS = 5


def _load_skills() -> dict:
    if not SKILLS_PATH.exists():
        return {}
    with open(SKILLS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _build_system_prompt(skills: dict) -> str:
    parts = [
        "你是经营数据与电子表数据解析助手。",
        "你仅根据工具返回的指标与结构化表格作答；禁止编造任何未在数据中出现的数值。",
        "若用户要求画图或制表，请调用 auto_generate_chart、generate_chart 或 generate_table，然后根据返回结果用自然语言简要说明。",
        "当用户只用自然语言描述想看的图，而未给出明确 sheet 名和列名时，应优先调用 auto_generate_chart，由后端自动匹配合适的表和字段。",
        "输出可包含结论、风险点、建议；若生成了图表或表格，在回复中简要描述即可，具体由前端渲染。",
    ]
    if skills:
        if skills.get("industry_terms"):
            parts.append("\n行业口径（简要）：" + " ".join(skills["industry_terms"][:6]))
        if skills.get("finance_terms"):
            parts.append("财务术语（简要）：" + " ".join(skills["finance_terms"][:5]))
        if skills.get("exception_templates"):
            parts.append("异常表述约束：" + " ".join(skills["exception_templates"][:4]))
    return "\n".join(parts)


def _ollama_base() -> str:
    base = (settings.ollama_url or "").rstrip("/")
    if not base:
        raise ValueError("Ollama 未配置，请在 .env 中设置 OLLAMA_URL")
    return base


def _get_tools_def() -> list[dict]:
    """Ollama /api/chat 所需的 tools 数组（OpenAI 兼容格式）。"""
    return [
        {
            "type": "function",
            "function": {
                "name": "read_metrics",
                "description": "获取当前 session 的表格结构摘要（只读）。返回各 sheet 的表名、列名、行数，无原始行数据。",
                "parameters": {
                    "type": "object",
                    "properties": {"session_id": {"type": "string", "description": "当前会话 ID"}},
                    "required": ["session_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "auto_generate_chart",
                "description": "根据用户的自然语言意图，自动选择合适的表、时间列与指标列并生成图表配置。适用于用户没有给出具体列名时的画图需求，例如「画一个利润趋势图」。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string", "description": "当前会话 ID"},
                        "intent": {
                            "type": "string",
                            "description": "用户用自然语言描述的画图意图，例如「画一个利润趋势图」「按项目看营收排名」。",
                        },
                        "preferred_chart_type": {
                            "type": "string",
                            "description": "可选，优先推荐的图表类型，如 line 或 bar。若缺省则由后端根据意图自动判断。",
                        },
                    },
                    "required": ["session_id", "intent"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "template_render",
                "description": "按模板名与变量渲染一段文本（如结论、风险、建议）。仅支持后端白名单模板。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "template_name": {"type": "string", "description": "模板名"},
                        "variables": {"type": "object", "description": "变量键值"},
                    },
                    "required": ["template_name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "generate_chart",
                "description": "根据指定 sheet 和列生成图表配置（Recharts 兼容）。sheet_name 为表名，x_column 为 X 轴列名，y_columns 为 Y 轴列名列表，chart_type 为 line/bar/pie。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "sheet_name": {"type": "string", "description": "工作表名称"},
                        "x_column": {"type": "string", "description": "X 轴对应的列名"},
                        "y_columns": {"type": "array", "items": {"type": "string"}, "description": "Y 轴列名列表"},
                        "chart_type": {"type": "string", "enum": ["line", "bar", "pie"], "description": "图表类型"},
                    },
                    "required": ["session_id", "sheet_name", "x_column", "y_columns", "chart_type"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "generate_table",
                "description": "根据 sheet_name 返回该表的表格数据（列名+行），可选 limit 限制行数。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "sheet_name": {"type": "string", "description": "工作表名称"},
                        "limit": {"type": "integer", "description": "最多返回行数，默认 100"},
                    },
                    "required": ["session_id", "sheet_name"],
                },
            },
        },
    ]


def _col_index(headers: list[str], name: str) -> int:
    """列名匹配（忽略首尾空格、大小写不敏感）。"""
    n = (name or "").strip().lower()
    for i, h in enumerate(headers):
        if (h or "").strip().lower() == n:
            return i
    return -1


def _to_num(v: Any) -> float:
    if v is None or v == "":
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _infer_metric_tag(col_name: str) -> str | None:
    """根据列名粗略推断财务语义标签（profit / revenue / cost 等）。"""
    name = (col_name or "").lower()
    if any(k in name for k in ["利润", "net_profit", "profit"]):
        return "profit"
    if any(k in name for k in ["收入", "营收", "turnover", "revenue", "sales", "流水"]):
        return "revenue"
    if any(k in name for k in ["成本", "支出", "费用", "cost", "expense"]):
        return "cost"
    return None


def _build_chart_spec_from_table(headers: list, rows: list[list], x_column: str, y_columns: list[str], chart_type: str) -> dict | None:
    """从通用表构建 Recharts 兼容的图表配置：xAxis.data + series[].name/data。"""
    xi = _col_index(headers, x_column)
    if xi < 0:
        return None
    y_indices = [_col_index(headers, y) for y in (y_columns or [])]
    if not y_indices or any(i < 0 for i in y_indices):
        return None
    x_vals = []
    series_data: list[list[float]] = [[] for _ in y_indices]
    for row in rows:
        if xi >= len(row):
            continue
        x_vals.append(str(row[xi]) if row[xi] is not None and row[xi] != "" else "")
        for k, yi in enumerate(y_indices):
            if yi < len(row):
                series_data[k].append(_to_num(row[yi]))
            else:
                series_data[k].append(0.0)
    series = []
    for k, col in enumerate(y_columns or []):
        series.append({"name": col, "type": "line" if chart_type == "line" else "bar", "data": series_data[k]})
    return {
        "xAxis": {"type": "category", "data": x_vals},
        "yAxis": {"type": "value"},
        "series": series,
    }


def _auto_pick_chart_from_intent(session_id: str, intent: str, preferred_chart_type: str | None = None) -> dict[str, Any]:
    """
    根据自然语言意图，结合 column_profiles 与原始表数据，自动选择合适的 sheet / 列并调用 generate_chart。
    返回与 generate_chart 相同结构的结果，或带 error 字段。
    """
    intent_l = (intent or "").lower()
    if not intent_l.strip():
        return {"error": "意图为空，无法自动生成图表。"}

    metrics = get_metrics(session_id)
    tables = get_tables(session_id)
    if not metrics or not tables:
        return {"error": "当前会话无可用表格数据，请先上传并解析 Excel。"}

    profiles_all = metrics.get("column_profiles") or {}
    validation = metrics.get("validation_summary") or {}

    # 粗粒度意图解析：趋势 → 折线；排名/对比 → 柱状
    chart_type = "bar"
    if preferred_chart_type:
        pt = preferred_chart_type.lower()
        if pt in ("line", "bar"):
            chart_type = pt
    else:
        if any(k in intent_l for k in ["趋势", "trend", "走势", "变化"]):
            chart_type = "line"
        elif any(k in intent_l for k in ["排名", "排行", "对比", "top", "排序"]):
            chart_type = "bar"
        else:
            # 默认时间相关问题用折线
            if any(k in intent_l for k in ["同比", "环比", "本年", "去年", "今年", "month", "year", "quarter"]):
                chart_type = "line"

    # 解析用户更关注哪类指标：利润 / 收入 / 成本
    desired_tag: str | None = None
    if any(k in intent_l for k in ["利润", "profit"]):
        desired_tag = "profit"
    elif any(k in intent_l for k in ["营收", "收入", "revenue", "sales", "流水"]):
        desired_tag = "revenue"
    elif any(k in intent_l for k in ["成本", "费用", "支出", "cost", "expense"]):
        desired_tag = "cost"

    best_choice: dict[str, Any] | None = None
    best_score = -1

    # 直接基于原始表 + 字段画像选列：尽量找一个「时间列 + 利润/营收类数值列」
    for sheet_name, t in tables.items():
        headers = t.get("headers") or []
        rows = t.get("rows") or []
        if not headers or not rows:
            continue
        sheet_profiles = profiles_all.get(sheet_name) or []
        if not sheet_profiles:
            continue

        sheet_validation = validation.get(sheet_name) or {}
        mixed_cols = set(sheet_validation.get("mixed_type_columns") or [])

        # 候选时间列：画像中 is_time=True，或者列名里有日期相关关键词
        time_candidates: list[str] = []
        for p in sheet_profiles:
            name = p.get("name") or ""
            lower_name = name.lower()
            if p.get("is_time") or any(k in lower_name for k in ["date", "day", "month", "year", "日期", "时间", "月份", "年度"]):
                if name in headers:
                    time_candidates.append(name)

        if not time_candidates:
            continue

        # 候选指标列：is_metric=True 为主，辅以列名关键词，并过滤掉混合类型列
        metric_candidates: list[str] = []
        for p in sheet_profiles:
            name = p.get("name") or ""
            if name not in headers:
                continue
            if name in mixed_cols:
                continue
            if not p.get("is_metric"):
                continue
            metric_candidates.append(name)

        if not metric_candidates:
            continue

        time_col = time_candidates[0]

        for m_name in metric_candidates:
            score = 0
            tag = _infer_metric_tag(m_name) or ""
            if desired_tag and tag == desired_tag:
                score += 5
            name_l = (m_name or "").lower()
            if desired_tag == "profit" and any(k in name_l for k in ["利润", "profit"]):
                score += 3
            if desired_tag == "revenue" and any(k in name_l for k in ["收入", "营收", "revenue", "sales", "turnover", "流水"]):
                score += 3
            if desired_tag == "cost" and any(k in name_l for k in ["成本", "费用", "支出", "cost", "expense"]):
                score += 3
            if chart_type == "line":
                score += 1

            if score > best_score:
                best_score = score
                best_choice = {
                    "sheet_name": sheet_name,
                    "x_column": time_col,
                    "y_columns": [m_name],
                    "chart_type": chart_type,
                }

    if best_choice is None:
        return {"error": "未能根据当前数据与意图自动匹配合适的图表，请在问题中注明表名和列名后重试。"}

    # 复用 generate_chart 逻辑
    inner_args = {
        "session_id": session_id,
        "sheet_name": best_choice["sheet_name"],
        "x_column": best_choice["x_column"],
        "y_columns": best_choice["y_columns"],
        "chart_type": best_choice["chart_type"],
    }
    result = execute_tool(session_id, "generate_chart", inner_args)
    if "error" in result:
        return result
    result["resolved"] = best_choice
    return result


def execute_tool(session_id: str, name: str, arguments: dict) -> dict[str, Any]:
    """执行指定工具，返回结果（可含 chart_spec/table_spec 供前端 Recharts/表格渲染）。"""
    if name == "read_metrics":
        sid = arguments.get("session_id") or session_id
        metrics = get_metrics(sid)
        if metrics is None:
            return {"error": "session 不存在或已过期"}
        return {
            "table_schemas": metrics.get("table_schemas", []),
            "column_profiles": metrics.get("column_profiles", {}),
            "aggregations": metrics.get("aggregations", {}),
            "validation_summary": metrics.get("validation_summary", {}),
        }

    if name == "template_render":
        template_name = arguments.get("template_name") or ""
        if template_name not in ("conclusion", "risk", "suggestion"):
            return {"error": "仅支持模板 conclusion / risk / suggestion"}
        variables = arguments.get("variables") or {}
        return {"text": f"[{template_name}] " + json.dumps(variables, ensure_ascii=False)}

    if name == "auto_generate_chart":
        sid = arguments.get("session_id") or session_id
        intent = (arguments.get("intent") or "").strip()
        preferred_chart_type = (arguments.get("preferred_chart_type") or "").strip() or None
        return _auto_pick_chart_from_intent(sid, intent, preferred_chart_type)

    if name == "generate_chart":
        sid = arguments.get("session_id") or session_id
        sheet_name = (arguments.get("sheet_name") or "").strip()
        x_column = (arguments.get("x_column") or "").strip()
        y_columns = arguments.get("y_columns") or []
        if isinstance(y_columns, str):
            y_columns = [y_columns]
        chart_type = (arguments.get("chart_type") or "bar").lower()
        if chart_type not in ("line", "bar", "pie"):
            chart_type = "bar"
        tables = get_tables(sid)
        if not tables or sheet_name not in tables:
            return {"error": f"未找到表「{sheet_name}」，可用表：{list(tables.keys()) if tables else '无'}"}
        t = tables[sheet_name]
        headers = t.get("headers") or []
        rows = t.get("rows") or []
        spec = _build_chart_spec_from_table(headers, rows, x_column, y_columns, chart_type)
        if not spec:
            return {"error": f"列「{x_column}」或「{y_columns}」不在表头 {headers} 中"}
        title = f"{sheet_name}: {x_column} vs {', '.join(y_columns)}"
        from backend.services.data_parse_session import append_kanban_chart
        append_kanban_chart(sid, {"id": f"chart_{sheet_name}_{x_column}", "title": title, "option": spec})
        return {"chart_spec": spec, "title": title}

    if name == "generate_table":
        sid = arguments.get("session_id") or session_id
        sheet_name = (arguments.get("sheet_name") or "").strip()
        limit = int(arguments.get("limit") or 100)
        limit = min(max(1, limit), 500)
        tables = get_tables(sid)
        if not tables or sheet_name not in tables:
            return {"error": f"未找到表「{sheet_name}」，可用表：{list(tables.keys()) if tables else '无'}"}
        t = tables[sheet_name]
        headers = t.get("headers") or []
        rows = (t.get("rows") or [])[:limit]
        str_rows = [[str(cell) if cell is not None else "" for cell in row] for row in rows]
        return {"table_spec": {"columns": headers, "rows": str_rows}}

    return {"error": f"未知工具 {name}"}


def _call_ollama_chat(messages: list[dict], tools: list[dict] | None = None) -> dict:
    """调用 Ollama POST /api/chat，返回完整 response（含 message）。"""
    base = _ollama_base()
    url = f"{base}/api/chat"
    model = getattr(settings, "ollama_model", None) or DEFAULT_MODEL
    payload = {"model": model, "messages": messages, "stream": False}
    if tools:
        payload["tools"] = tools
    return post_json_with_guard(url=url, payload=payload, timeout_s=90.0, kind="data_parse.chat")


def _extract_json(text: str) -> dict | None:
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass
    for pattern in [r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", r"(\{[\s\S]*\})"]:
        m = re.search(pattern, text)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                continue
    return None


def _should_direct_auto_chart(user_message: str) -> bool:
    """
    粗粒度判断：是否可以直接走后端 auto_generate_chart，而不依赖 LLM 自己决定是否调用工具。
    场景：用户明显在要求“画某个指标的趋势/排名图”，例如「画一个利润趋势图」「按项目看营收排名」。
    """
    msg = (user_message or "").strip()
    if not msg:
        return False
    m = msg.lower()
    # 是否提到图表 / 画图
    has_chart_intent = any(k in m for k in ["画", "趋势图", "趋势", "图", "plot", "chart", "可视化"])
    # 是否提到典型经营指标
    has_metric = any(
        k in m
        for k in [
            "利润",
            "profit",
            "营收",
            "收入",
            "revenue",
            "sales",
            "流水",
            "成本",
            "费用",
            "支出",
            "cost",
            "expense",
        ]
    )
    return bool(has_chart_intent and has_metric)


def generate_analysis(session_id: str) -> str:
    """
    首轮 LLM 解读：根据表格结构摘要（table_schemas）生成简要概述，不传原始行数据。
    """
    schemas = get_table_schemas(session_id)
    if not schemas:
        return "当前无解析数据，请先上传并解析 Excel。"
    base = _ollama_base()
    url = f"{base}/api/generate"
    model = getattr(settings, "ollama_model", None) or DEFAULT_MODEL
    skills = _load_skills()
    system = _build_system_prompt(skills)
    data_summary = json.dumps([{"sheet_name": s.get("sheet_name"), "headers": s.get("headers"), "row_count": s.get("row_count")} for s in schemas], ensure_ascii=False, indent=0)
    prompt = f"{system}\n\n请根据以下表格结构摘要（仅表名、列名、行数，无原始行）给出简要概述：有哪些表、主要列含义、可做哪些分析。禁止编造具体数值。\n\n结构摘要：\n{data_summary}\n\n请用简洁的 Markdown 输出：## 概述 / ## 可分析方向。"
    payload = {"model": model, "prompt": prompt, "stream": False}
    try:
        out_json = post_json_with_guard(url=url, payload=payload, timeout_s=60.0, kind="data_parse.analysis")
        out = (out_json.get("response") or "").strip()
        return out or "未能生成解读。"
    except Exception as e:
        logger.warning("Ollama 解读失败: %s", e)
        return "解读生成失败，请检查 Ollama 服务。"


def chat(session_id: str, user_message: str) -> dict[str, Any]:
    """
    多轮对话：支持工具调用（read_metrics, generate_chart, generate_table 等）。
    返回 { "reply": str, "chart_spec": dict|None, "table_spec": dict|None }。
    """
    if not get_session(session_id):
        return {"reply": "会话不存在或已过期，请重新上传表格。", "chart_spec": None, "table_spec": None}

    # 一类高频且规则明确的需求（如「画一个利润趋势图」），直接由后端触发 auto_generate_chart，
    # 避免完全依赖 LLM 自己是否调用工具，从而提升可预测性与成功率。
    if _should_direct_auto_chart(user_message):
        auto_res = _auto_pick_chart_from_intent(session_id, user_message, None)
        if "chart_spec" in auto_res:
            resolved = auto_res.get("resolved") or {}
            reply = (
                f"已根据当前表自动生成「{resolved.get('sheet_name', '')}」中"
                f"列「{', '.join(resolved.get('y_columns') or [])}」的趋势图。"
            )
            return {"reply": reply, "chart_spec": auto_res["chart_spec"], "table_spec": None}
        # 若自动匹配失败，直接返回明确的错误信息，不再交给 LLM 编造「尚未上传」之类回复。
        err_msg = auto_res.get("error") or "未能根据当前数据与意图自动匹配合适的图表，请在问题中补充表名和列名后重试。"
        return {"reply": err_msg, "chart_spec": None, "table_spec": None}

    skills = _load_skills()
    system = _build_system_prompt(skills)
    tools_def = _get_tools_def()

    from backend.services.data_parse_session import append_chat_history, get_chat_history

    history = get_chat_history(session_id)
    messages = [{"role": "system", "content": system}]
    for h in history:
        messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": user_message})

    chart_spec_out = None
    table_spec_out = None
    reply_text = ""

    for _ in range(MAX_TOOL_ROUNDS):
        try:
            resp = _call_ollama_chat(messages, tools=tools_def)
        except Exception as e:
            logger.warning("Ollama chat 失败: %s", e)
            return {"reply": "对话请求失败，请检查 Ollama 服务。", "chart_spec": None, "table_spec": None}

        msg = resp.get("message") or {}
        content = (msg.get("content") or "").strip()
        tool_calls = msg.get("tool_calls") or []

        if not tool_calls:
            reply_text = content
            break

        messages.append({"role": "assistant", "content": content or "(调用工具)", "tool_calls": tool_calls})
        for tc in tool_calls:
            fn = tc.get("function") or {}
            name = fn.get("name") or ""
            raw_args = fn.get("arguments")
            # Ollama 在部分版本中会直接返回 dict 类型的 arguments，这里同时兼容 str 与 dict
            if isinstance(raw_args, dict):
                args = raw_args
            else:
                args_str = raw_args or "{}"
                try:
                    args = json.loads(args_str) if args_str else {}
                except json.JSONDecodeError:
                    args = {}
            result = execute_tool(session_id, name, args)
            if isinstance(result.get("chart_spec"), dict):
                chart_spec_out = result["chart_spec"]
            if isinstance(result.get("table_spec"), dict):
                table_spec_out = result["table_spec"]
            tool_msg = {"role": "tool", "content": json.dumps(result, ensure_ascii=False)}
            if tc.get("id"):
                tool_msg["tool_call_id"] = tc["id"]
            messages.append(tool_msg)

        reply_text = content or "已执行工具，请查看图表或表格。"

    append_chat_history(session_id, "user", user_message)
    append_chat_history(session_id, "assistant", reply_text)

    return {"reply": reply_text, "chart_spec": chart_spec_out, "table_spec": table_spec_out}
