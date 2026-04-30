"""
数据解析对话：Ollama /api/chat + 工具（read_metrics, template_render, generate_chart, generate_table）。
仅基于 session 内聚合数据，不把原始行级数据拼进 prompt。
"""
import json
import logging
import re
import statistics
from pathlib import Path
from typing import Any

import httpx

from backend.config import settings
from backend.services.ollama_guard import post_json_with_guard
from backend.services.upstream_guard import assert_upstream_allowed
from backend.services.agent_skills_loader import build_system_addon_for_enabled_skills
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


def _build_system_prompt(skills: dict, *, playbook_addon: str = "", prompt_addon: str = "") -> str:
    # playbook_addon：历史命名；现为「已启用技能的 SKILL.md 等 system 追加段」
    parts = [
        "你是经营数据与电子表数据解析助手。",
        "当前已绑定解析会话：服务端会在 system 末尾附带「当前会话表结构快照」；回答前仍应调用 read_metrics 以获取列画像与校验摘要。若快照中已有工作表，禁止声称「未绑定」「无有效表格」或「请先上传」。",
        "你仅根据工具返回的指标与结构化表格作答；禁止编造任何未在数据中出现的数值。",
        "若用户要求画图或制表，请调用 auto_generate_chart、generate_chart 或 generate_table，然后根据返回结果用自然语言简要说明。",
        "当用户只用自然语言描述想看的图，而未给出明确 sheet 名和列名时，应优先调用 auto_generate_chart，由后端自动匹配合适的表和字段。",
        "若用户要求「美化电子表」等 Excel 格式类需求：诚实说明当前工具链不支持单元格样式/主题；可建议用 generate_chart / generate_table 或 auto_generate_chart 提升可读性，并先 read_metrics。",
        "输出可包含结论、风险点、建议；若生成了图表或表格，在回复中简要描述即可，具体由前端渲染。",
    ]
    if skills:
        if skills.get("industry_terms"):
            parts.append("\n行业口径（简要）：" + " ".join(skills["industry_terms"][:6]))
        if skills.get("finance_terms"):
            parts.append("财务术语（简要）：" + " ".join(skills["finance_terms"][:5]))
        if skills.get("exception_templates"):
            parts.append("异常表述约束：" + " ".join(skills["exception_templates"][:4]))
    out = "\n".join(parts)
    if playbook_addon.strip():
        out = out + "\n\n" + playbook_addon.strip()
    if prompt_addon.strip():
        pa = prompt_addon.strip()
        if len(pa) > 6000:
            pa = pa[:6000] + "\n…（已截断）"
        out = out + "\n\n## 用户勾选的提示词资产（摘要/正文拼接）\n" + pa
    return out


def _session_table_bootstrap(session_id: str) -> str:
    """
    将当前会话的表结构摘要直接拼入 system，避免模型在未成功调用 read_metrics 时
    编造「未绑定」「无有效表格」等与前端状态矛盾的表述。
    """
    s = get_session(session_id)
    if not s:
        return ""
    schemas = s.get("table_schemas") or []
    tables = s.get("tables") or {}
    lines: list[str] = []
    if schemas:
        for row in schemas[:40]:
            lines.append(
                json.dumps(
                    {
                        "sheet_name": row.get("sheet_name"),
                        "headers": row.get("headers"),
                        "row_count": row.get("row_count"),
                    },
                    ensure_ascii=False,
                )
            )
    elif isinstance(tables, dict) and tables:
        for name, t in list(tables.items())[:40]:
            headers = (t or {}).get("headers") or []
            nrows = len((t or {}).get("rows") or [])
            lines.append(json.dumps({"sheet_name": name, "headers": headers, "row_count": nrows}, ensure_ascii=False))
    val = s.get("validation_summary") or {}
    val_str = json.dumps(val, ensure_ascii=False)[:2500] if val else "{}"
    header = (
        "\n\n## 当前会话表结构快照（已由服务端自动注入）\n"
        "以下每行 JSON 描述一个工作表：名称、列名、行数。回答「各工作表用途/风险/结构」类问题时**必须以此为准**。\n"
        "**禁止**声称「当前会话未绑定」「未绑定有效表格」「无表格数据」等，除非下方快照明确无任何工作表行。\n"
        "行级具体数值仍须通过 read_metrics / 工具返回使用，勿凭想象填写单元格。\n"
    )
    if not lines:
        return header + "_（解析结果中无工作表：table_schemas 与 tables 均为空）_\n"
    body = "\n".join(lines)
    if len(body) > 10000:
        body = body[:10000] + "\n…（表结构快照已截断）"
    extra = ""
    if val_str and val_str != "{}":
        extra = f"\n\n## validation_summary（摘录）\n{val_str}"
    return header + body + extra


def _should_direct_sheet_usage_risk(user_message: str) -> bool:
    """
    结构型问题（各工作表用途/主要风险）容易被模型编造“未绑定/无表格/缺失比例”等。
    对这类问题直接由后端基于 session 的 table_schemas/tables/validation_summary 生成确定性答复。
    """
    msg = (user_message or "").strip()
    if not msg:
        return False
    m = msg.lower()
    has_sheet = ("工作表" in msg) or ("sheet" in m) or ("表1" in msg) or ("表2" in msg)
    has_usage = ("用途" in msg) or ("用来" in msg) or ("做什么" in msg)
    has_risk = ("风险" in msg) or ("缺失" in msg) or ("质量" in msg) or ("可信" in msg) or ("异常" in msg)
    has_analysis_ask = ("分析" in msg) or ("总结" in msg) or ("概述" in msg) or ("主要" in msg)
    # “请根据已上传的表格/列出各工作表用途与主要风险” 这种典型问法
    if has_sheet and has_usage and has_risk:
        return True
    # “分析经营的主要风险（勿编造具体表述）” 这类风险分析问法，也走后端确定性逻辑
    return bool(has_risk and has_analysis_ask)


def _build_sheet_usage_risk_reply(session_id: str) -> str:
    s = get_session(session_id) or {}
    schemas = s.get("table_schemas") or []
    tables = s.get("tables") or {}
    val = s.get("validation_summary") or {}

    # 统一从 schemas 取结构；若缺失则从 tables 推导
    items: list[dict[str, Any]] = []
    if isinstance(schemas, list) and schemas:
        for row in schemas:
            if not isinstance(row, dict):
                continue
            items.append(
                {
                    "sheet_name": row.get("sheet_name"),
                    "headers": row.get("headers") or [],
                    "row_count": row.get("row_count"),
                    "is_main_sheet": bool(row.get("is_main_sheet")),
                }
            )
    elif isinstance(tables, dict) and tables:
        for name, t in tables.items():
            headers = (t or {}).get("headers") or []
            rows = (t or {}).get("rows") or []
            items.append({"sheet_name": name, "headers": headers, "row_count": len(rows), "is_main_sheet": False})

    if not items:
        return "当前会话已绑定，但解析结果中没有任何工作表结构可用（table_schemas 与 tables 均为空）。请换一份含有效表格的 Excel 后重新上传。"

    # 逐表生成确定性风险点（不编造百分比）
    lines: list[str] = []
    lines.append("已检测到以下工作表（基于服务端解析结构快照；不包含行级明细）：")
    for it in items[:20]:
        name = str(it.get("sheet_name") or "").strip() or "(未命名工作表)"
        headers = it.get("headers") if isinstance(it.get("headers"), list) else []
        row_count = it.get("row_count")
        try:
            rc = int(row_count) if row_count is not None else None
        except Exception:
            rc = None
        total_cols = len(headers)
        empty_cols = sum(1 for h in headers if not str(h or "").strip())
        nonempty_cols = total_cols - empty_cols
        risks: list[str] = []
        if total_cols == 0:
            risks.append("未解析到表头（无法判断字段含义）")
        if empty_cols > 0:
            risks.append(f"表头存在空列名：{empty_cols} 列（建议在 Excel 补齐字段名或删除空列）")
        if rc is not None and rc <= 3:
            risks.append(f"行数较少：{rc} 行（趋势/对比结论可能不稳健）")
        if nonempty_cols <= 3 and total_cols > 3:
            risks.append(f"有效字段较少：非空列名仅 {nonempty_cols} 列（其余多为空列名）")

        usage_guess = "用于按时间/维度查看经营指标（如收入、利润等）的汇总或明细"  # 仅为通用用途，不给具体口径
        # 若主表标记为 true，更偏“主分析表”
        if it.get("is_main_sheet"):
            usage_guess = "主分析表：适合做趋势/对比/排名等经营指标分析（具体以字段含义为准）"

        lines.append(f"\n- 工作表「{name}」")
        lines.append(f"  - 用途：{usage_guess}")
        lines.append(f"  - 结构：列数 {total_cols}（非空列名 {nonempty_cols}），行数 {rc if rc is not None else '未知'}")
        if risks:
            lines.append("  - 主要风险：")
            for r in risks[:6]:
                lines.append(f"    - {r}")
        else:
            lines.append("  - 主要风险：未发现明显结构性风险（如需更细粒度缺失/类型检查，可继续深挖）")

        # FP&A 风格补充：趋势/波动/异常/集中度（仅基于当前会话数据，确定性计算）
        tb = (tables or {}).get(name) if isinstance(tables, dict) else None
        if isinstance(tb, dict):
            hdrs = [str(x or "").strip() for x in (tb.get("headers") or [])]
            rws = tb.get("rows") or []
            if hdrs and rws:
                # 时间列与指标列识别（轻量启发）
                time_idx = -1
                for i, h in enumerate(hdrs):
                    hl = h.lower()
                    if any(k in hl for k in ["日期", "时间", "月份", "month", "date", "year", "季度", "quarter"]):
                        time_idx = i
                        break
                metric_idx = -1
                priority_keys = ["净利润", "利润", "营收", "收入", "流水", "成本", "费用", "profit", "revenue", "cost", "expense"]
                for i, h in enumerate(hdrs):
                    hl = h.lower()
                    vals = [row[i] for row in rws if isinstance(row, list) and i < len(row)]
                    num_vals = [float(v) for v in vals if _is_numeric_like(v)]
                    ratio = (len(num_vals) / len(vals)) if vals else 0.0
                    if ratio < 0.6:
                        continue
                    if metric_idx < 0:
                        metric_idx = i
                    if any(k in hl for k in priority_keys):
                        metric_idx = i
                        break
                if metric_idx >= 0:
                    seq = []
                    for row in rws:
                        if not isinstance(row, list) or metric_idx >= len(row):
                            continue
                        v = row[metric_idx]
                        if _is_numeric_like(v):
                            seq.append(float(v))
                    if len(seq) >= 2:
                        first, last = seq[0], seq[-1]
                        change_pct = None
                        if abs(first) > 1e-9:
                            change_pct = (last - first) / abs(first) * 100.0
                        mean_abs = sum(abs(x) for x in seq) / len(seq) if seq else 0.0
                        stdev = statistics.pstdev(seq) if len(seq) >= 2 else 0.0
                        cv = (stdev / mean_abs * 100.0) if mean_abs > 1e-9 else None
                        # 异常点：|z|>2
                        outlier_cnt = 0
                        if len(seq) >= 3 and stdev > 1e-9:
                            m0 = statistics.mean(seq)
                            for x in seq:
                                z = (x - m0) / stdev
                                if abs(z) >= 2.0:
                                    outlier_cnt += 1
                        # 集中度：Top3 占比
                        top3_ratio = None
                        abs_vals = sorted([abs(x) for x in seq], reverse=True)
                        s_all = sum(abs_vals)
                        if s_all > 1e-9:
                            top3_ratio = sum(abs_vals[:3]) / s_all * 100.0

                        metric_name = hdrs[metric_idx] or f"列{metric_idx + 1}"
                        lines.append("  - 经营分析（FP&A 启发）：")
                        if change_pct is not None:
                            direction = "上升" if change_pct >= 0 else "下降"
                            lines.append(f"    - 趋势：{metric_name} 从首期到末期总体{direction}，变动约 {change_pct:.1f}%。")
                        else:
                            lines.append(f"    - 趋势：{metric_name} 可用于趋势分析（首期基数为 0，未给出百分比变化）。")
                        if cv is not None:
                            vol = "高" if cv >= 30 else ("中" if cv >= 15 else "低")
                            lines.append(f"    - 波动：{metric_name} 变异系数约 {cv:.1f}%（波动{vol}）。")
                        if outlier_cnt > 0:
                            lines.append(f"    - 异常：检测到约 {outlier_cnt} 个疑似异常点（|z|>=2，建议复核）。")
                        if top3_ratio is not None:
                            lines.append(f"    - 集中度：{metric_name} Top3 观测值占比约 {top3_ratio:.1f}%。")

    # validation_summary 只做“存在性提示”，避免模型把它扩写成虚构百分比
    if isinstance(val, dict) and val:
        keys = [k for k in val.keys()][:10]
        lines.append(f"\n补充：本次解析带有 validation_summary（字段：{', '.join(map(str, keys))}）。如需更细粒度缺失/类型/异常提示，我可以继续展开。")
    else:
        lines.append("\n补充：如需更细粒度缺失/类型/异常提示，我可以继续展开。")

    return "\n".join(lines).strip()


def _should_direct_metric_lookup(user_message: str) -> bool:
    msg = (user_message or "").strip()
    if not msg:
        return False
    has_metric = any(k in msg for k in ["流水", "营收", "收入", "净利润", "成本", "费用"])
    has_query = any(k in msg for k in ["如何", "多少", "怎么样", "情况", "是多少", "?","？"])
    return bool(has_metric and has_query)


def _build_metric_lookup_reply(session_id: str, user_message: str) -> str:
    tables = get_tables(session_id) or {}
    if not tables:
        return "当前会话已绑定，但解析结果中没有任何工作表数据。请换一份含有效表格的 Excel 后重新上传。"

    q = (user_message or "").strip()
    m = re.search(r"([\u4e00-\u9fa5A-Za-z0-9_\-]{1,40})的(流水|营收|收入|净利润|成本|费用)", q)
    keyword = (m.group(1) if m else "").strip()
    metric_word = (m.group(2) if m else "")

    metric_alias = {
        "流水": ["流水", "营收", "收入", "revenue", "sales", "turnover"],
        "营收": ["营收", "收入", "revenue", "sales", "turnover"],
        "收入": ["收入", "营收", "revenue", "sales", "turnover"],
        "净利润": ["净利润", "利润", "profit"],
        "成本": ["成本", "支出", "费用", "cost", "expense"],
        "费用": ["费用", "支出", "成本", "cost", "expense"],
    }
    keys = metric_alias.get(metric_word or "流水", metric_alias["流水"])

    def _pick_metric_col(headers: list[str]) -> int:
        for i, h in enumerate(headers):
            hl = str(h or "").lower()
            if any(k in hl for k in keys):
                return i
        # 次优：第一列含“金额/值”的列
        for i, h in enumerate(headers):
            hl = str(h or "").lower()
            if any(k in hl for k in ["金额", "数值", "value", "amt"]):
                return i
        return -1

    matches: list[tuple[str, float | None]] = []
    checked_sheets: list[str] = []
    metric_cols_found: list[str] = []
    for sheet_name, t in tables.items():
        headers = [str(x or "").strip() for x in (t.get("headers") or [])]
        rows = t.get("rows") or []
        checked_sheets.append(str(sheet_name))
        mi = _pick_metric_col(headers)
        if mi >= 0:
            metric_cols_found.append(f"{sheet_name}.{headers[mi]}")
        if not keyword:
            continue
        for row in rows:
            text = " ".join(str(c) for c in (row or []))
            if keyword not in text:
                continue
            val = None
            if mi >= 0 and isinstance(row, list) and mi < len(row):
                try:
                    val = float(row[mi])
                except (TypeError, ValueError):
                    val = None
            matches.append((sheet_name, val))

    if not keyword:
        return (
            "当前会话有效。若要查询某对象的指标，请使用“<对象>的<指标>如何”格式，例如“项目A的流水如何”。"
            f"当前已解析工作表：{'、'.join(checked_sheets[:5])}。"
        )

    if not matches:
        # 兜底：转置表结构（第一行是对象，第一列是指标）识别
        # 例：表头 ["流水","破天一剑"]，行 ["本年累计",10], ["目标",100]
        for sheet_name, t in tables.items():
            headers = [str(x or "").strip() for x in (t.get("headers") or [])]
            rows = t.get("rows") or []
            if not headers or not rows or not keyword:
                continue
            if keyword not in headers:
                continue
            col_idx = headers.index(keyword)
            # 指标主题可在第 0 列表头，也可能在行标签
            metric_theme = headers[0] if headers else ""
            metric_like = any(k in (metric_theme or "") for k in keys) or metric_word in (metric_theme or "")
            if not metric_like:
                # 若主题不匹配，再看行标签里是否出现 metric 词
                row_label_hit = False
                for row in rows:
                    if not isinstance(row, list) or not row:
                        continue
                    lbl = str(row[0] or "").strip()
                    if any(k in lbl for k in keys):
                        row_label_hit = True
                        break
                if not row_label_hit:
                    continue

            def _row_label(row: list[Any]) -> str:
                return str(row[0] if row else "").strip()

            preferred_order = ["本年累计", "累计", "本年", "实际", "当前", "值", "流水", "营收", "收入"]
            picked_row = None
            for pref in preferred_order:
                for row in rows:
                    if not isinstance(row, list):
                        continue
                    if col_idx >= len(row):
                        continue
                    if pref in _row_label(row) and _is_numeric_like(row[col_idx]):
                        picked_row = row
                        break
                if picked_row is not None:
                    break
            if picked_row is None:
                for row in rows:
                    if not isinstance(row, list):
                        continue
                    if col_idx < len(row) and _is_numeric_like(row[col_idx]):
                        picked_row = row
                        break
            if picked_row is not None:
                cur_label = _row_label(picked_row) or "当前值"
                cur_val = float(picked_row[col_idx])
                target_val = None
                for row in rows:
                    if not isinstance(row, list):
                        continue
                    lbl = _row_label(row)
                    if col_idx < len(row) and any(k in lbl for k in ["目标", "预算", "plan", "target"]) and _is_numeric_like(row[col_idx]):
                        target_val = float(row[col_idx])
                        break
                if target_val is not None and abs(target_val) > 1e-9:
                    ratio = cur_val / target_val * 100.0
                    return (
                        f"已在「{sheet_name}」识别到「{keyword}」的{metric_word or '指标'}："
                        f"{cur_label}={cur_val:.2f}，目标={target_val:.2f}，完成率约 {ratio:.1f}%。"
                    )
                return f"已在「{sheet_name}」识别到「{keyword}」的{metric_word or '指标'}：{cur_label}={cur_val:.2f}。"

        cols = "、".join(metric_cols_found[:6]) if metric_cols_found else "（未识别到明确的指标列）"
        return (
            f"当前会话有效，但未在已解析数据中检索到与「{keyword}」相关的记录。"
            f"已检索工作表：{'、'.join(checked_sheets[:5])}；可用指标列：{cols}。"
            "请核对关键词是否与表内文本一致，或提供具体 sheet/列名后我继续定位。"
        )

    vals = [v for _s, v in matches if isinstance(v, float)]
    if vals:
        total = sum(vals)
        return (
            f"已在当前会话中检索到与「{keyword}」相关记录 {len(matches)} 条，"
            f"匹配到的“{metric_word or '指标'}”数值合计约为 {total:.2f}。"
            "如需我展开到按月份/按工作表明细，请继续指定维度。"
        )
    return (
        f"已在当前会话中检索到与「{keyword}」相关记录 {len(matches)} 条，"
        f"但未能稳定解析出“{metric_word or '指标'}”数值列。"
        "请提供具体 sheet 与列名，我可直接返回明细表。"
    )


def _ollama_base() -> str:
    base = (settings.ollama_url or "").rstrip("/")
    if not base:
        raise ValueError("Ollama 未配置，请在 .env 中设置 OLLAMA_URL")
    assert_upstream_allowed(base, service_name="Ollama")
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


def _safe_header_name(v: Any) -> str:
    s = str(v or "").strip()
    return s


def _is_numeric_like(v: Any) -> bool:
    if v is None or (isinstance(v, str) and not v.strip()):
        return False
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False


def _pick_fallback_chart_choice(tables: dict[str, dict[str, Any]], chart_type: str) -> dict[str, Any] | None:
    """
    当 column_profiles 不完整或判定失败时的兜底策略：
    - 优先选第一个有数据的 sheet
    - x 轴优先时间相关列名，否则第一列非空列名
    - y 轴优先“数值占比最高”的列，且不与 x 同列
    """
    for sheet_name, t in (tables or {}).items():
        headers_raw = t.get("headers") or []
        rows = t.get("rows") or []
        headers = [_safe_header_name(h) for h in headers_raw]
        if not rows or not headers:
            continue

        nonempty = [(i, h) for i, h in enumerate(headers) if h]
        if not nonempty:
            continue

        time_idx = -1
        for i, h in nonempty:
            hl = h.lower()
            if any(k in hl for k in ["日期", "时间", "月份", "month", "date", "year", "季度", "quarter"]):
                time_idx = i
                break
        if time_idx < 0:
            time_idx = nonempty[0][0]
        x_col = headers[time_idx]

        best_y_idx = -1
        best_ratio = -1.0
        for i, h in nonempty:
            if i == time_idx:
                continue
            vals = [row[i] for row in rows if isinstance(row, list) and i < len(row)]
            if not vals:
                continue
            num_cnt = sum(1 for v in vals if _is_numeric_like(v))
            ratio = num_cnt / max(1, len(vals))
            if ratio > best_ratio:
                best_ratio = ratio
                best_y_idx = i
        if best_y_idx < 0:
            # 如果都不像数值列，也至少给一个可画的列，避免“生成图表”直接失败
            for i, _h in nonempty:
                if i != time_idx:
                    best_y_idx = i
                    break
        if best_y_idx < 0:
            continue
        y_col = headers[best_y_idx]
        if not x_col or not y_col:
            continue
        return {
            "sheet_name": sheet_name,
            "x_column": x_col,
            "y_columns": [y_col],
            "chart_type": chart_type,
        }
    return None


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
    if tables is None or metrics is None:
        return {"error": "会话不存在或已过期（例如后端已重启）。请在本页重新上传 Excel 以创建新会话。"}
    if not tables:
        return {"error": "当前会话已绑定，但解析结果中没有任何工作表数据。请换一份含有效表格的 Excel 后重新上传。"}

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
        best_choice = _pick_fallback_chart_choice(tables, chart_type)
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


def _looks_like_session_missing_reply(text: str) -> bool:
    t = (text or "").lower()
    if not t:
        return False
    patterns = [
        "会话不存在",
        "session 不存在",
        "session不存在",
        "会话未绑定",
        "未绑定有效表格",
        "请先上传",
    ]
    return any(p in t for p in patterns)


def _build_session_valid_hint(session_id: str) -> str:
    tables = get_tables(session_id) or {}
    if not tables:
        return "当前会话已绑定，但解析结果中没有任何工作表数据。请换一份含有效表格的 Excel 后重新上传。"
    names = list(tables.keys())
    show = "、".join(names[:5])
    more = "" if len(names) <= 5 else f" 等 {len(names)} 张"
    return f"当前会话有效，已解析到工作表：{show}{more}。如需具体分析，请明确指标/表名，或让我先调用 read_metrics。"


def _should_direct_auto_chart(user_message: str, session_id: str | None = None) -> bool:
    """
    粗粒度判断：是否可以直接走后端 auto_generate_chart，而不依赖 LLM 自己决定是否调用工具。
    场景：用户明显在要求“画某个指标的趋势/排名图”，例如「画一个利润趋势图」「按项目看营收排名」。
    含「生成图表」等短指令且当前会话已有表数据时，也走自动匹配（避免仅因缺少“利润”等词而失败）。
    """
    msg = (user_message or "").strip()
    if not msg:
        return False
    m = msg.lower()
    # 是否提到图表 / 画图
    has_chart_intent = any(
        k in m for k in ["画", "生成图表", "作图", "出图", "趋势图", "趋势", "图", "plot", "chart", "可视化"]
    )
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
    tables_ok = False
    if session_id:
        t = get_tables(session_id)
        tables_ok = bool(t and len(t) > 0)
    explicit_chart = "生成图表" in msg or "帮我画图" in msg or "画个图" in msg
    return bool(has_chart_intent and (has_metric or (explicit_chart and tables_ok) or (tables_ok and ("图" in msg or "chart" in m))))


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


def chat(
    session_id: str,
    user_message: str,
    *,
    enabled_skills: list[str] | None = None,
    prompt_addon: str | None = None,
) -> dict[str, Any]:
    """
    多轮对话：支持工具调用（read_metrics, generate_chart, generate_table 等）。
    返回 { "reply": str, "chart_spec": dict|None, "table_spec": dict|None }。

    enabled_skills：AI 互动工作流传入；与 manifest 登记一致的 ID 会将对应 SKILL.md 正文注入 system（可多选叠加）。
    prompt_addon：由前端将勾选的 prompt.* 摘要/正文拼接后注入 system（服务端截断）。
    """
    if not get_session(session_id):
        return {"reply": "会话不存在或已过期，请重新上传表格。", "chart_spec": None, "table_spec": None}

    skill_ids = [str(x).strip() for x in (enabled_skills or []) if str(x).strip()]
    skill_md_addon = build_system_addon_for_enabled_skills(skill_ids)

    # 结构型问法：直接由后端确定性生成（避免模型编造“无表/缺失比例”等）
    if _should_direct_sheet_usage_risk(user_message):
        reply = _build_sheet_usage_risk_reply(session_id)
        return {"reply": reply, "chart_spec": None, "table_spec": None}
    # 指标检索类问法（如“xx 的流水如何”）：直接后端检索，避免模型误报 session 失效
    if _should_direct_metric_lookup(user_message):
        reply = _build_metric_lookup_reply(session_id, user_message)
        return {"reply": reply, "chart_spec": None, "table_spec": None}

    # 一类高频且规则明确的需求（如「画一个利润趋势图」），直接由后端触发 auto_generate_chart，
    # 避免完全依赖 LLM 自己是否调用工具，从而提升可预测性与成功率。
    if _should_direct_auto_chart(user_message, session_id):
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
    system = (
        _build_system_prompt(
            skills,
            playbook_addon=skill_md_addon,
            prompt_addon=(prompt_addon or "").strip(),
        )
        + _session_table_bootstrap(session_id)
    )
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

    from backend.services.data_parse_output_validate import append_output_shape_audit

    reply_text = append_output_shape_audit(reply_text, prompt_addon=prompt_addon)
    # 防幻觉兜底：会话有效时，禁止输出“会话不存在/未绑定”等错误结论。
    if _looks_like_session_missing_reply(reply_text):
        if _should_direct_sheet_usage_risk(user_message):
            reply_text = _build_sheet_usage_risk_reply(session_id)
        else:
            reply_text = _build_session_valid_hint(session_id)

    append_chat_history(session_id, "user", user_message)
    append_chat_history(session_id, "assistant", reply_text)

    return {"reply": reply_text, "chart_spec": chart_spec_out, "table_spec": table_spec_out}


def chat_multi(
    session_ids: list[str],
    user_message: str,
    *,
    enabled_skills: list[str] | None = None,
    prompt_addon: str | None = None,
) -> dict[str, Any]:
    """
    多会话聚合（多 Excel 并存）：
    - deterministic 路由优先：风险分析/指标检索/生成图表
    - 其它问题默认使用第一个会话（primary）走原 chat
    """
    ids = [str(x).strip() for x in (session_ids or []) if str(x).strip()]
    if not ids:
        return {"reply": "缺少 session_id，请先上传并解析 Excel。", "chart_spec": None, "table_spec": None}
    # 去重保序
    seen = set()
    ids = [x for x in ids if not (x in seen or seen.add(x))]
    primary = ids[0]

    # 若只有一个会话，直接走原逻辑
    if len(ids) == 1:
        return chat(primary, user_message, enabled_skills=enabled_skills, prompt_addon=prompt_addon)

    # 指标检索：在所有会话里找“能给出值/完成率”的那一个
    if _should_direct_metric_lookup(user_message):
        best = None
        for sid in ids:
            if not get_session(sid):
                continue
            txt = _build_metric_lookup_reply(sid, user_message)
            if "完成率" in txt or re.search(r"\b\d+\.\d{2}\b", txt):
                return {"reply": txt, "chart_spec": None, "table_spec": None}
            best = best or txt
        return {"reply": best or _build_session_valid_hint(primary), "chart_spec": None, "table_spec": None}

    # 风险/用途：合并输出（按会话分组）
    if _should_direct_sheet_usage_risk(user_message):
        parts: list[str] = []
        for sid in ids:
            if not get_session(sid):
                continue
            parts.append(f"### 会话 {sid[:8]}…\n{_build_sheet_usage_risk_reply(sid)}")
        if parts:
            return {"reply": "\n\n".join(parts).strip(), "chart_spec": None, "table_spec": None}
        return {"reply": "所有会话均不存在或已过期，请重新上传表格。", "chart_spec": None, "table_spec": None}

    # 生成图表：优先 primary，失败则遍历
    if _should_direct_auto_chart(user_message, primary) or ("生成图表" in (user_message or "") and user_message.strip() == "生成图表"):
        for sid in ids:
            if not get_session(sid):
                continue
            auto_res = _auto_pick_chart_from_intent(sid, user_message, None)
            if "chart_spec" in auto_res:
                resolved = auto_res.get("resolved") or {}
                reply = (
                    f"已根据当前表自动生成「{resolved.get('sheet_name', '')}」中"
                    f"列「{', '.join(resolved.get('y_columns') or [])}」的趋势图。"
                )
                return {"reply": reply, "chart_spec": auto_res["chart_spec"], "table_spec": None}
        # 都失败
        return {"reply": "未能在已绑定的任一表中自动匹配合适的图表。请说明要画的指标/表名/列名。", "chart_spec": None, "table_spec": None}

    # 其它：默认使用 primary（MVP：后续可做跨 session 工具调用）
    return chat(primary, user_message, enabled_skills=enabled_skills, prompt_addon=prompt_addon)
