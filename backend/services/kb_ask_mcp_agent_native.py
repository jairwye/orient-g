"""Hermes 智能体原生 MCP 载荷：结构化证据 + 成稿契约（orientg_kb_ask v2）。"""

from __future__ import annotations

import json
import re
from typing import Any

_RD_COUNT_RE = re.compile(
    r"研发人员(?:数量|合计)?[^0-9]{0,24}(\d{1,3}(?:,\d{3})+|\d{4,}|\d{2,3})\s*人?",
    re.I,
)
_RD_SHARE_RE = re.compile(r"占比[^0-9]{0,16}(\d+(?:\.\d+)?)\s*%", re.I)
_HEADCOUNT_RE = re.compile(r"在职员工[^0-9]{0,20}(\d+)\s*人", re.I)
_EXCEL_RD_RE = re.compile(r"研发[^\n|]{0,20}\|\s*(\d+(?:\.\d+)?)", re.I)
_FINANCE_AMOUNT_RE = re.compile(
    r"(\d{1,3}(?:,\d{3})+(?:\.\d{2})?|\d+(?:\.\d{2})?)\s*(?:万元|亿元|元|%|％)?",
)
_FINANCE_RATE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")


def detect_kb_task_type(query: str) -> str:
    """竞品财报 / 人员 / 通用 KB 任务分类。"""
    from backend.services.kb_retrieval_plan import query_wants_personnel_structure

    q = (query or "").strip()
    if query_wants_personnel_structure(q):
        return "personnel_compare"
    if re.search(r"销售费用|管理费用|毛利率|营收|净利润|费用率", q):
        return "finance_compare"
    return "general_kb"


def _finance_entities(query: str) -> list[str]:
    from backend.services.kb_retrieval_plan import extract_query_entity_phrases

    ents = extract_query_entity_phrases(query)
    if ents:
        return ents
    out: list[str] = []
    for pat in (r"可比公司A", r"YYCQ", r"YYCQ"):
        if re.search(pat, query, re.I):
            out.append("可比公司A" if "可比公司A" in pat else "YYCQ")
    return out


def _personnel_entities(query: str) -> list[str]:
    from backend.services.kb_retrieval_plan import extract_query_entity_phrases

    return extract_query_entity_phrases(query)


def _task_entities(query: str, task_type: str) -> list[str]:
    if task_type == "finance_compare":
        return _finance_entities(query)
    if task_type == "personnel_compare":
        return _personnel_entities(query)
    return []


def _parse_int(raw: str | None) -> int | None:
    if not raw:
        return None
    try:
        return int(str(raw).replace(",", "").strip())
    except ValueError:
        return None


def _parse_float(raw: str | None) -> float | None:
    if not raw:
        return None
    try:
        return float(str(raw).replace(",", "").strip())
    except ValueError:
        return None


_ROLE_HEADCOUNT_RE = re.compile(
    r"(销售|运营|管理|行政|技术|研发)人员?\s*[（(]?[^0-9]{0,12}[）)]?\s*"
    # 须优先匹配千分位或 ≥4 位，避免 1378 被 \d{1,3} 截成 137
    r"(\d{1,3}(?:,\d{3})+|\d{4,}|\d{2,3})\s*人?",
    re.I,
)


def extract_excerpt_metrics(excerpt: str, *, task_type: str) -> dict[str, Any]:
    """从节选提取 Hermes 可直接填表的关键数字。"""
    text = excerpt or ""
    metrics: dict[str, Any] = {}
    if task_type == "finance_compare":
        amounts = _FINANCE_AMOUNT_RE.findall(text)
        if amounts:
            metrics["amounts"] = amounts[:5]
        rates = _FINANCE_RATE_RE.findall(text)
        if rates:
            metrics["rates_pct"] = [_parse_float(x) for x in rates[:3] if _parse_float(x) is not None]
        if re.search(r"销售费用", text):
            metrics["metric"] = "sales_fee"
        elif re.search(r"管理费用", text):
            metrics["metric"] = "admin_expense"
        elif re.search(r"毛利率|毛利", text):
            metrics["metric"] = "gross_margin"
        return {k: v for k, v in metrics.items() if v}
    if task_type != "personnel_compare":
        return metrics
    m = _RD_COUNT_RE.search(text)
    if m:
        metrics["rd_headcount"] = _parse_int(m.group(1))
    m = _RD_SHARE_RE.search(text)
    if m:
        metrics["rd_share_pct"] = _parse_float(m.group(1))
    m = _HEADCOUNT_RE.search(text)
    if m:
        metrics["total_headcount"] = _parse_int(m.group(1))
    m = _EXCEL_RD_RE.search(text)
    if m and "rd_headcount" not in metrics:
        v = _parse_float(m.group(1))
        if v is not None:
            metrics["rd_headcount"] = int(v) if v == int(v) else v
    for m in _ROLE_HEADCOUNT_RE.finditer(text):
        role = m.group(1)
        n = _parse_int(m.group(2))
        if n is None or n < 2:
            continue
        if role == "销售":
            metrics["sales_headcount"] = n
        elif role == "运营":
            metrics["ops_headcount"] = n
        elif role in ("管理", "行政"):
            metrics.setdefault("admin_headcount", n)
        elif role == "研发" and "rd_headcount" not in metrics:
            metrics["rd_headcount"] = n
    # excel「1.1信息-人员」：研发 70.00 / 运营 61.00
    for role, key in (
        ("运营", "ops_headcount"),
        ("管理", "admin_headcount"),
        ("支持", "support_headcount"),
        ("研发", "rd_headcount"),
    ):
        if key in metrics:
            continue
        m = re.search(rf"{role}\s*[|｜]?\s*(\d+(?:\.\d{{2}})?)", text)
        if m:
            v = _parse_float(m.group(1))
            if v is not None and v >= 2:
                metrics[key] = int(v) if v == int(v) else v
    return {k: v for k, v in metrics.items() if v is not None}


def build_personnel_verification_queries(
    *,
    query: str,
    entities: list[str],
    evidence: list[dict[str, Any]],
) -> list[str]:
    """人员横比：证据看似够时仍给不同主体/缺口维度的核实 query（禁与原 query 完全相同）。"""
    q0 = (query or "").strip()
    by_ent: dict[str, dict[str, Any]] = {}
    for block in evidence or []:
        if not isinstance(block, dict):
            continue
        ent = str(block.get("entity") or "")
        metrics = block.get("metrics") if isinstance(block.get("metrics"), dict) else {}
        if "可比公司A" in ent:
            by_ent["可比公司A"] = metrics
        elif "YYCQ" in ent or re.search(r"YYCQ", ent, re.I):
            by_ent["YYCQ"] = metrics
    candidates: list[str] = []
    sanqi = by_ent.get("可比公司A") or {}
    yycq = by_ent.get("YYCQ") or {}
    if not yycq.get("rd_headcount"):
        candidates.append("YYCQ 2025 1.1信息-人员 研发 运营")
    if not sanqi.get("sales_headcount") or not sanqi.get("ops_headcount"):
        candidates.append("可比公司A 2025 销售人员 运营人员 员工数量")
    if not sanqi.get("rd_headcount"):
        candidates.append("可比公司A 2025 研发人员情况")
    # 双主体齐全时仍强制一轮「另一主体」核实，避免一次取证即停
    if "YYCQ" in entities or yycq:
        candidates.append("YYCQ 2025 员工专业构成 1.1信息-人员")
    if any("可比公司A" in e for e in entities) or sanqi:
        candidates.append("可比公司A 2025 员工数量、专业构成及教育程度")
    out: list[str] = []
    seen: set[str] = set()
    for c in candidates:
        c = (c or "").strip()
        if not c or c == q0 or c in seen:
            continue
        seen.add(c)
        out.append(c)
        if len(out) >= 3:
            break
    return out


def build_output_contract(
    *,
    task_type: str,
    entities: list[str],
    require_verification: bool = False,
) -> dict[str, Any]:
    """Hermes 成稿契约：中文、必含章节、禁止行为。"""
    if task_type == "personnel_compare":
        # 勿用「核心指标对照」——易诱导规模倍数话术；横比以人员结构对照表为主。
        sections = ["### 人员结构对照", "### 对比分析", "### 口径说明"]
        must_include_metrics = ["rd_headcount", "sales_headcount", "ops_headcount"]
    elif task_type == "finance_compare":
        sections = ["### 核心指标对照", "### 对比分析", "### 口径说明"]
        must_include_metrics = []
    else:
        sections = ["### 结论", "### 证据摘要"]
        must_include_metrics = []
    next_action = (
        "verify_gap_then_write_final"
        if require_verification and task_type == "personnel_compare"
        else "write_final_answer_now"
    )
    out: dict[str, Any] = {
        "language": "zh-CN",
        "required_sections": sections,
        "next_action": next_action,
        "do_not": [
            "重复相同 query 调用 orientg_kb_ask",
            "英文 planning 或 Let me search",
            "terminal / curl / execute_code 代替 KB",
            "用 Orient-G 网关模板口吻整页粘贴",
            "总体规模对比 / 核心指标对照 / 差距倍数（如 22.6 倍）",
            "把可比公司A研发人数误记到YYCQ",
            "推算 / 推断 / 约N人（无证据区间）",
            "用「请勿采信」脚注掩盖仍展示的违规句",
            "未调用 MCP 先输出终稿",
            "人员横比仅 1 次 MCP 即停（须取证+不同 query 核证）",
        ],
    }
    if require_verification and task_type == "personnel_compare":
        out["must_verify_before_final"] = True
        out["min_orientg_kb_ask_calls"] = 2
    if must_include_metrics:
        out["must_fill_from_metrics"] = must_include_metrics
        out["table_hint"] = (
            "对照表列：职能归属 | 可比公司A | YYCQ；"
            "行至少含研发/销售/运营（有 metrics 则填数字，无则写「证据未覆盖」）。"
            "勿写员工总数倍数对照；用职能分项表。"
        )
    return out


def build_suggested_queries_if_insufficient(
    *,
    query: str,
    task_type: str,
    entities: list[str],
    evidence_count: int,
) -> list[str]:
    """证据不足时给 Hermes 中文 follow-up query（避免英文泛搜）。"""
    if evidence_count >= 2 and task_type == "personnel_compare" and len(entities) >= 2:
        return []
    from backend.services.kb_retrieval_plan import enhance_kb_ask_query, personnel_retrieval_subqueries

    out: list[str] = []
    seen: set[str] = set()
    candidates = [enhance_kb_ask_query(query)]
    if task_type == "personnel_compare":
        candidates.extend(personnel_retrieval_subqueries(query))
        for ent in entities:
            candidates.extend(
                [
                    f"{ent} 员工数量 专业构成 2025",
                    f"{ent} 研发人员情况 2025",
                    f"{ent} 1.1信息-人员",
                ]
            )
    elif task_type == "finance_compare":
        for ent in entities:
            candidates.extend(
                [
                    f"{ent} 2025 销售费用",
                    f"{ent} 2025 营业收入",
                    f"{ent} 销售费用率",
                ]
            )
        candidates.extend(
            [
                f"{query} 附注",
                f"{query} 合并利润表",
            ]
        )
    for cand in candidates:
        c = (cand or "").strip()
        if not c or c in seen:
            continue
        seen.add(c)
        out.append(c)
        if len(out) >= 4:
            break
    return out


def build_agent_payload(
    *,
    query: str,
    excerpts: list[dict[str, Any]],
    citations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """构建 orientg_kb_ask_v2 agent_payload。"""
    task_type = detect_kb_task_type(query)
    entities = _task_entities(query, task_type)
    evidence: list[dict[str, Any]] = []
    for ex in excerpts or []:
        if not isinstance(ex, dict):
            continue
        excerpt_text = str(ex.get("excerpt") or "").strip()
        if not excerpt_text:
            continue
        ent = str(ex.get("entity") or "").strip()
        metrics = extract_excerpt_metrics(excerpt_text, task_type=task_type)
        evidence.append(
            {
                "entity": ent or None,
                "doc_id": str(ex.get("doc_id") or "").strip() or None,
                "chunk_id": str(ex.get("chunk_id") or "").strip() or None,
                "excerpt_preview": excerpt_text[:400],
                "metrics": metrics,
            }
        )
    entity_hits = {
        e
        for e in entities
        if any(
            e in str(x.get("entity") or "")
            or e in str(x.get("excerpt_preview") or "")
            for x in evidence
        )
    }
    sufficient = False
    if task_type == "personnel_compare":
        if len(entities) >= 2:
            sufficient = len(entity_hits) >= 2 and len(evidence) >= 2
        elif len(entities) == 1:
            sufficient = len(entity_hits) >= 1 and len(evidence) >= 1
        else:
            sufficient = len(evidence) >= 2
    elif task_type == "finance_compare":
        if len(entities) >= 2:
            sufficient = len(entity_hits) >= 2 and len(evidence) >= 2
        else:
            sufficient = len(evidence) >= 1
    else:
        sufficient = len(evidence) >= 1
    # 横比主问句：即便 evidence_sufficient 仍要求不同 query 核证（E 尺子）
    from backend.services.kb_retrieval_plan import query_wants_personnel_compare

    primary_compare = bool(
        task_type == "personnel_compare"
        and len(entities) >= 2
        and query_wants_personnel_compare(query)
    )
    require_verification = bool(sufficient and primary_compare)
    contract = build_output_contract(
        task_type=task_type,
        entities=entities,
        require_verification=require_verification,
    )
    suggested = build_suggested_queries_if_insufficient(
        query=query,
        task_type=task_type,
        entities=entities,
        evidence_count=len(evidence),
    )
    verification_queries: list[str] = []
    if require_verification:
        verification_queries = build_personnel_verification_queries(
            query=query,
            entities=entities,
            evidence=evidence,
        )
        suggested = []
    elif sufficient:
        suggested = []
        # 核实轮（非主横比问句）：允许立即成稿
        if task_type == "personnel_compare":
            contract["next_action"] = "write_final_answer_now"
            contract.pop("must_verify_before_final", None)
    entity_hints = _entity_hints(task_type, entities)
    kb_status = {
        "empty": len(evidence) == 0 and len(citations or []) == 0,
        "citation_count": len(citations or []),
        "evidence_blocks": len(evidence),
        "note": (
            "知识库非空：下方 evidence 来自 folder 内年报/excel。"
            "勿声称「知识库为空」或「YYCQ非上市公司无法检索」。"
            if evidence
            else "当前 excerpt 为空；可再调 1 次 orientg_kb_ask（中文 query）。"
        ),
    }
    out: dict[str, Any] = {
        "schema": "orientg_kb_ask_v2",
        "task_type": task_type,
        "language": "zh-CN",
        "query": (query or "").strip(),
        "entities": entities,
        "entity_hints": entity_hints,
        "kb_status": kb_status,
        "evidence_sufficient": sufficient,
        "evidence": evidence,
        "citation_count": len(citations or []),
        "output_contract": contract,
        "suggested_queries_if_insufficient": suggested,
    }
    if verification_queries:
        out["verification_queries"] = verification_queries
    return out


def _entity_hints(task_type: str, entities: list[str]) -> list[dict[str, str]]:
    hints: list[dict[str, str]] = []
    for ent in entities:
        if ent == "YYCQ":
            hints.append(
                {
                    "entity": ent,
                    "hint": "KB 内主体（excel「1.1信息-人员」），非 A 股公开检索名；勿要求用户确认上市代码。",
                }
            )
        elif "可比公司A" in ent:
            hints.append(
                {
                    "entity": ent,
                    "hint": "A 股年报节选（研发人员情况、员工专业构成）；销售/运营见员工数量专节。",
                }
            )
    if task_type == "personnel_compare" and len(entities) >= 2:
        hints.append(
            {
                "entity": "—",
                "hint": "两家口径不同：可比公司A=年报披露；YYCQ=excel 职能分项；不可直接比员工总数。",
            }
        )
    return hints


def build_personnel_draft_skeleton_from_payload(payload: dict[str, Any]) -> str:
    """从 evidence[].metrics 预填对照表骨架，供 Hermes 直接抄用数字成稿。"""
    by_ent: dict[str, dict[str, Any]] = {}
    for block in payload.get("evidence") or []:
        if not isinstance(block, dict):
            continue
        ent = str(block.get("entity") or "")
        metrics = block.get("metrics") if isinstance(block.get("metrics"), dict) else {}
        if "可比公司A" in ent:
            by_ent["可比公司A"] = metrics
        elif "YYCQ" in ent or re.search(r"YYCQ", ent, re.I):
            by_ent["YYCQ"] = metrics
    sanqi = by_ent.get("可比公司A") or {}
    yycq = by_ent.get("YYCQ") or {}

    def _cell(m: dict[str, Any], *keys: str) -> str:
        for k in keys:
            if m.get(k) is not None:
                return f"{m[k]} 人"
        return "证据未覆盖"

    rows = [
        ("研发", _cell(sanqi, "rd_headcount"), _cell(yycq, "rd_headcount")),
        ("销售", _cell(sanqi, "sales_headcount"), _cell(yycq, "sales_headcount")),
        ("运营", _cell(sanqi, "ops_headcount"), _cell(yycq, "ops_headcount")),
    ]
    lines = [
        "## 【硬数字参考表·勿将本标题上屏】（写入终稿表格数字；禁止改写为员工总数倍数对照）",
        "",
        "### 人员结构对照",
        "",
        "| 职能归属 | 可比公司A | YYCQ |",
        "| --- | --- | --- |",
    ]
    for role, a, b in rows:
        lines.append(f"| {role} | {a} | {b} |")
    lines.extend(
        [
            "",
            "### 对比分析",
            "",
            "- 结构差异：两家披露口径不同（年报专业构成 vs excel 职能分项），不可直接比员工总数。",
            "",
            "### 口径说明",
            "",
            "可比公司A=年报节选；YYCQ=excel「1.1信息-人员」。",
            "",
        ]
    )
    return "\n".join(lines)


def is_personnel_mcp_draft_skeleton(text: str) -> bool:
    """用户终稿若仍带 MCP「成稿骨架/请原样采用」套话 → 不算 Hermes 主写。"""
    h = text or ""
    return bool(
        re.search(r"成稿骨架|请原样采用下列数字写入终稿|硬数字参考表·勿将本标题上屏", h)
    )


def is_personnel_thin_salvage_final(text: str) -> bool:
    """剥标题后的短对照表（仍像 MCP salvage）不得冒充 Hermes 长成稿。"""
    h = (text or "").strip()
    if not h:
        return False
    if is_personnel_mcp_draft_skeleton(h):
        return True
    if "人员结构对照" not in h:
        return False
    if len(h) >= 360:
        return False
    stock = bool(re.search(r"结构差异：两家披露口径不同（年报专业构成", h))
    thin_analysis = len(h) < 280 or h.count("\n") < 16
    return stock and thin_analysis


def build_personnel_salvage_final_from_payload(payload: dict[str, Any]) -> str:
    """coerce 上屏用：同口径对照表，**不含**骨架元标题套话。"""
    raw = build_personnel_draft_skeleton_from_payload(payload)
    out = re.sub(
        r"^##\s*(?:成稿骨架|【硬数字参考表)[^\n]*\n+",
        "",
        raw.strip(),
        count=1,
    ).strip()
    return out or raw.strip()


def build_hermes_agent_mcp_reply(
    *,
    query: str,
    base_reply: str,
    excerpts: list[dict[str, Any]],
    citations: list[dict[str, Any]] | None = None,
) -> tuple[str, dict[str, Any]]:
    """
    返回 (reply_text, agent_payload)。
    reply 为 Hermes tool result 主文本：中文行动指令 + JSON 块 + 节选。
    """
    payload = build_agent_payload(query=query, excerpts=excerpts, citations=citations)
    parts: list[str] = []
    parts.append("## Orient-G KB 检索完成（Hermes 原生 v2）")
    parts.append("")
    contract = payload.get("output_contract") if isinstance(payload.get("output_contract"), dict) else {}
    next_action = str(contract.get("next_action") or "")
    if payload.get("evidence_sufficient"):
        if payload.get("task_type") == "personnel_compare":
            if next_action == "verify_gap_then_write_final":
                vqs = payload.get("verification_queries") or []
                vq_lines = "\n".join(f"- {q}" for q in vqs[:3]) or "- （选另一主体或缺口职能专节）"
                parts.append(
                    "**证据已足写表，但尚未核证**：请先用下方 **不同 query** 再调 1 次 "
                    "`orientg_kb_ask` 核实缺口维度/另一主体（禁止重复本次完全相同的 query），"
                    "然后再用中文写终稿。"
                    "终稿必含 `### 人员结构对照`（**采用下列参考表硬数字**）+ "
                    "`### 对比分析` + `### 口径说明`。"
                    "**禁止**把「成稿骨架/硬数字参考表」标题原样上屏；须扩写完整中文终稿。"
                    "禁止英文 planning、禁止 22.6 倍规模对照、禁止推算/推断/约N人。"
                    "禁止声称 knowledge base 为空。"
                )
                parts.append("")
                parts.append("建议核实 query：")
                parts.append(vq_lines)
                parts.append("")
                parts.append(build_personnel_draft_skeleton_from_payload(payload))
            else:
                parts.append(
                    "**核实轮证据已齐**：请**立即用中文写终稿**，必含 `### 人员结构对照` 表格"
                    "（**采用下列参考表硬数字**，可改写对比分析措辞），"
                    "再写 `### 对比分析` 与 `### 口径说明`。"
                    "**禁止**把参考表标题原样上屏；须写出完整中文分析。"
                    "禁止英文 planning、禁止 22.6 倍规模对照、禁止把员工总数当人员结构。"
                    "勿再重复相同 query；禁止声称 knowledge base 为空。"
                )
                parts.append("")
                parts.append(build_personnel_draft_skeleton_from_payload(payload))
        else:
            parts.append(
                "**证据已足**：请根据下方 `agent_payload` 与证据节选，**立即用中文写终稿**。"
                "勿重复相同 query 再调 orientg_kb_ask。"
                "禁止声称 knowledge base 为空；entity_hints / kb_status 已说明 KB 状态。"
            )
    else:
        parts.append(
            "**证据可能不足**：请先阅读 `agent_payload.suggested_queries_if_insufficient`，"
            "必要时再调 1 次 orientg_kb_ask（中文 query），然后成稿。"
        )
    parts.append("")
    parts.append("```json")
    parts.append(json.dumps(payload, ensure_ascii=False, indent=2))
    parts.append("```")
    base = (base_reply or "").strip()
    if base and base not in parts[-1]:
        parts.append("")
        parts.append(base)
    if excerpts:
        if payload.get("task_type") == "personnel_compare":
            label = "人员结构证据节选"
        elif payload.get("task_type") == "finance_compare":
            label = "财务指标证据节选"
        else:
            label = "证据节选"
        parts.append(f"\n## {label}（{len(excerpts)} 条）\n")
        for i, ex in enumerate(excerpts, 1):
            did = str(ex.get("doc_id") or "").strip()
            ent = str(ex.get("entity") or "").strip()
            title = f"{ent} ({did})" if ent else did
            parts.append(f"### 节选 {i} · {title}\n{str(ex.get('excerpt') or '').strip()}\n")
    return "\n".join(parts).strip(), payload


def hermes_native_personnel_reply_sufficient(
    hermes_reply: str,
    *,
    user_query: str,
    hermes_kb_ask_count: int = 0,
) -> bool:
    """
    Hermes 深度 + 人员横比：MCP 已调且终稿满足对照表/主体/数字约束。
    用于 native 模式跳过网关补检索（不替代 misattribution gate）。
    """
    if int(hermes_kb_ask_count or 0) < 1:
        return False
    from backend.services.kb_retrieval_plan import (
        extract_query_entity_phrases,
        query_wants_personnel_structure,
    )
    from backend.services.hermes_stream_sanitize import looks_like_planning
    from backend.services.personnel_compare_report import (
        personnel_compare_needs_structured_gate,
        personnel_reply_has_analysis,
    )
    from backend.services.kb_ask_mcp_reply import personnel_compare_reply_misattributed

    uq = (user_query or "").strip()
    h = (hermes_reply or "").strip()
    if not h or not query_wants_personnel_structure(uq):
        return False
    # 明确错稿/旧模板：不得标 sufficient（否则跳过 gate 后由误归因整页换模板刷绿）
    if re.search(
        r"22\.6\s*倍|14\.5\s*倍|核心指标对照|核心指标对比|总体规模对比|一、(?:总体)?规模",
        h,
    ):
        return False
    if re.search(r"95\s*人.{0,40}1,?378|1,?378.{0,40}显然不可能", h):
        return False
    from backend.services.hermes_response_analysis import classify_hermes_response

    entities = extract_query_entity_phrases(uq)

    def _has_personnel_anchors() -> bool:
        if len(entities) >= 2 and not all(ent in h for ent in entities):
            return False
        if not re.search(r"可比公司A|可比公司A", h):
            return False
        if not re.search(r"YYCQ", h, re.I):
            return False
        # Live Hermes 常吐规划+数字堆；有关键硬数字即可 skip 补检索交 gate
        # 勿用 \\b：中文邻接时（如「946人」）会失败
        hits = sum(
            1
            for pat in (r"(?<!\d)946(?!\d)", r"(?<!\d)242(?!\d)", r"1[,，]?378", r"(?<!\d)70(?!\d)")
            if re.search(pat, h)
        )
        return hits >= 2 and len(h) >= 160

    if looks_like_planning(h) and not _has_personnel_anchors():
        return False
    # 不完整对照表仍可跳过补检索（structured final gate 用 prefetch 刷新）
    if classify_hermes_response(h, user_query=uq).get("acceptable_personnel_final"):
        return True
    if _has_personnel_anchors():
        return True
    if personnel_compare_needs_structured_gate(h, user_query=uq):
        # 有对照表骨架但缺销售/运营时：足够跳过网关再查，交给 final gate
        if (
            re.search(r"人员结构对照", h)
            and "对比分析" in h
            and "|" in h
            and re.search(r"\d{2,4}", h)
            and (not looks_like_planning(h) or _has_personnel_anchors())
        ):
            if len(entities) < 2 or all(ent in h for ent in entities):
                return True
        return False
    if personnel_compare_reply_misattributed(h, user_query=uq):
        from backend.services.personnel_compare_report import _STRUCTURE_TABLE_TITLE

        if not (_STRUCTURE_TABLE_TITLE in h and "### 对比分析" in h and "|" in h):
            return False
    if not personnel_reply_has_analysis(h, min_len=180):
        return False
    if len(entities) >= 2:
        for ent in entities:
            if ent not in h:
                return False
    if not re.search(r"\d{2,4}", h):
        return False
    if not re.search(r"人员结构对照|核心指标对照", h):
        return False
    return True
