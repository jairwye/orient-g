"""Hermes 流式正文清洗：推理/脚本进 thinking，用户可见答案进 delta。"""

from __future__ import annotations

import re

# 计划/反思类（应进入执行过程，而非主气泡正文）
_PLANNING_MARKERS = (
    "用户要求",
    "步骤：",
    "步骤:",
    "先尝试",
    "让我再次",
    "让我再",
    "让我先",
    "我将",
    "检索关键词",
    "根据 `orientg",
    "根据 orientg",
    "orientg-debugging",
    "partial_pnl_data",
    "知识库中**缺失**",
    "知识库中缺失",
    "知识库中不包含",
    "无法提供研发费用",
    "无法提供研发费用的对比",
    "知识库中明确不包含",
    "无法提供销售费用明细",
    "我将如实告知",
    "后端服务正常",
    "后端正常",
    "需再次尝试检索",
    "skill不相关",
    "这个 skill",
    "让我直接输出",
    "预检索证据",
    "先根据已有证据",
    "不需要加载",
    "定向补检索",
    "Evidence Pack",
    "预检索 JSON",
    "需要确认合并",
    "需要确认母公司",
)

# 用户可见报告常见起点
_REPLY_START_MARKERS = (
    "\n### ",
    "\n## ",
    "\n**结论",
    "\n结论：",
    "\n| 项目",
    "\n| :---",
    "\n|项目",
    "。###",
    "。## ",
    "对比分析报告。###",
    "---#",
    "\n---\n#",
)

_REPORT_TITLE_START = re.compile(
    r"(?:---+\s*)?(?:#{1,3}\s*(?:华清|结论|\S{2,40}(?:对比分析|分析报告)))",
)

_CODE_EXEC_PATTERNS = re.compile(
    r"(import\s+urllib|curl\s+-[sX]|TOKEN=\$\(|urllib\.request\.Request|subprocess\.|os\.system\()",
    re.I,
)


def looks_like_code_execution(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if _CODE_EXEC_PATTERNS.search(t):
        return True
    if "login_url" in t and "urllib" in t:
        return True
    return False


def looks_like_planning(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if looks_like_code_execution(t):
        return True
    hits = sum(1 for m in _PLANNING_MARKERS if m in t)
    if hits >= 2:
        return True
    if hits >= 1 and len(t) < 400:
        return True
    if "partial_pnl_data" in t or "orientg-debugging" in t:
        return True
    if "知识库中" in t and ("缺失" in t or "不包含" in t) and "无法提供" in t:
        return True
    if t.startswith("用户要求"):
        return True
    if t.startswith("根据 orientg") or t.startswith("根据`orientg") or "根据 `orientg" in t[:80]:
        return True
    if re.match(r"^Based on (?:the )?Evidence Pack", t, re.I):
        return True
    if "No additional API calls are needed" in t and len(t) < 600:
        return True
    if "orientg_kb_ask" in t and len(t) < 1200:
        return True
    if "skill" in t.lower() and ("不相关" in t or "不需要加载" in t):
        return True
    return False


def _looks_like_orchestration_preamble(prefix: str) -> bool:
    t = (prefix or "").strip()
    if not t:
        return False
    if looks_like_planning(t):
        return True
    if _planning_ratio(t) >= 0.35:
        return True
    if "orientg_kb_ask" in t or "预检索" in t or t.startswith("Evidence Pack"):
        return True
    if re.search(r"skill", t, re.I) and ("不相关" in t or "调试" in t):
        return True
    return False


def strip_hermes_orchestration_preamble(text: str) -> str:
    """去掉 Hermes 终稿前的编排/工具选型过程稿（Runs 单轮时常见）。"""
    t = (text or "").strip()
    if not t:
        return ""
    t = re.sub(
        r"^Based on (?:the )?Evidence Pack provided,[^。.\n]*(?:needed|calls)[^。.\n]*[。.]?\s*",
        "",
        t,
        flags=re.I,
    )
    t = re.sub(
        r"^Based on (?:the )?Evidence Pack[^。.\n]*[。.]?\s*",
        "",
        t,
        flags=re.I,
    )
    t = re.sub(
        r"^No additional API calls are needed\.?\s*",
        "",
        t,
        flags=re.I,
    )
    for anchor in ("让我直接输出：", "让我直接输出:", "让我直接输出"):
        if anchor in t:
            t = t.split(anchor, 1)[-1].strip()
    m = _REPORT_TITLE_START.search(t)
    if m and m.start() > 0:
        prefix = t[: m.start()]
        if _looks_like_orchestration_preamble(prefix):
            t = t[m.start() :].lstrip("-").strip()
    t = re.sub(r"^-{2,}\s*", "", t)
    return t


def classify_hermes_stream_chunk(text: str) -> str:
    """
    返回 thinking | delta | skip。
    thinking：进入 agentReasoning / 执行过程，不计入最终 reply。
    """
    t = text or ""
    if not t.strip():
        return "skip"
    if looks_like_code_execution(t):
        return "thinking"
    if looks_like_planning(t):
        return "thinking"
    return "delta"


def _planning_ratio(prefix: str) -> float:
    t = (prefix or "").strip()
    if not t:
        return 0.0
    hits = sum(1 for m in _PLANNING_MARKERS if m in t)
    if looks_like_code_execution(t):
        return 1.0
    if hits >= 2:
        return 0.85
    if hits == 1 and len(t) > 80:
        return 0.55
    return 0.0


def extract_user_facing_reply(text: str) -> str:
    """从 Hermes 累积文本中剥离前置推理，保留报告正文。"""
    t = (text or "").strip()
    if not t:
        return ""
    best = len(t)
    for m in _REPLY_START_MARKERS:
        idx = t.find(m)
        if idx != -1 and idx < best:
            best = idx
    if best > 0 and best < len(t):
        prefix = t[:best]
        if _planning_ratio(prefix) >= 0.5 or looks_like_code_execution(prefix):
            return t[best:].lstrip()
    if _planning_ratio(t) >= 0.7 and best == len(t):
        return ""
    return strip_hermes_orchestration_preamble(t)


_FORBIDDEN_ESTIMATE = re.compile(
    r"约\s*[\d,.]+|[\d]{1,3}\s*[-~至]\s*[\d]{1,3}\s*万|减少约|增加约|变动情况：.*约"
)


def reply_has_unsupported_breakdown_amounts(text: str) -> bool:
    """估算区间或反推计算的分项金额（均不可作为终稿分项）。"""
    from backend.services.evidence_reply_align import reply_has_derived_breakdown_amounts

    t = text or ""
    if reply_has_unsupported_estimates(t):
        return True
    return reply_has_derived_breakdown_amounts(t)


def reply_has_verifiable_breakdown_table(text: str, *, min_data_rows: int = 2) -> bool:
    """终稿是否已有可渲染的分项对比表（Markdown pipe 或已转换 TSV）。"""
    data_rows = 0
    for ln in (text or "").splitlines():
        if ln.count("|") < 2:
            continue
        if re.match(r"\s*\|[-:\s|]+\|\s*$", ln):
            continue
        if re.search(r"\d{1,3}(?:,\d{3})+\.\d{2}", ln):
            data_rows += 1
    return data_rows >= min_data_rows


def _is_markdown_table_line(ln: str) -> bool:
    return ln.count("|") >= 2


def _strip_unsupported_estimate_prose(text: str) -> str:
    """保留对比表；去掉正文中「约 xx 万」等估算句，避免误触发「无分项」占位。"""
    from backend.services.evidence_reply_align import reply_has_derived_breakdown_amounts

    out: list[str] = []
    for ln in (text or "").split("\n"):
        if _is_markdown_table_line(ln):
            out.append(ln)
            continue
        if reply_has_unsupported_estimates(ln) or reply_has_derived_breakdown_amounts(ln):
            cleaned = _FORBIDDEN_ESTIMATE.sub("", ln)
            cleaned = re.sub(r"\s+", " ", cleaned).strip()
            if len(cleaned) >= 12 and not reply_has_unsupported_estimates(cleaned):
                out.append(cleaned)
            continue
        out.append(ln)
    return "\n".join(out).strip()

# 面向用户的终稿：去掉 LLM 内联引用标记（citations 面板仍保留）
_INLINE_SOURCE_MARKER = re.compile(
    r"\s*\[(?:doc_chunk|evidence_pack|doc_id|document|source|chunk_id)[^\]]*\]\s*",
    re.I,
)
_INLINE_DOC_ID_PAREN = re.compile(r"\s*\((?:doc_id|document|来源)[^)]*\)", re.I)
_INLINE_DOC_ID_BACKTICK = re.compile(r"\s*(?:doc_id|document_id|docling)[:\s]*`[^`]+`", re.I)
_INLINE_UD_ID = re.compile(r"\s*\bud_[a-f0-9]{16,32}\b\s*", re.I)
_INLINE_DOC_CHUNK_HASH = re.compile(r"\s*#ud_[a-f0-9]{16,32}_s\d+\s*", re.I)


def strip_inline_source_markers(text: str) -> str:
    """去掉正文中的 [doc_chunk …] / doc_id / ud_* 等内联标记。"""
    t = text or ""
    t = _INLINE_SOURCE_MARKER.sub(" ", t)
    t = _INLINE_DOC_ID_PAREN.sub("", t)
    t = _INLINE_DOC_ID_BACKTICK.sub("", t)
    t = _INLINE_UD_ID.sub(" ", t)
    t = _INLINE_DOC_CHUNK_HASH.sub(" ", t)
    t = re.sub(r"\s*\[来源[^\]]*\]\s*", " ", t)
    t = re.sub(r"证据\s*`(?:\s*[^`]*\s*)?`\s*", "证据 ", t)
    t = re.sub(r"`\s*`", "", t)
    t = re.sub(r"\(doc_id:\s*\)", "", t, flags=re.I)
    t = re.sub(r"[（(]\s*[）)]", "", t)
    t = re.sub(r"[ \t]{2,}", " ", t)
    t = re.sub(r" \n", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def format_hermes_draft_trace(text: str, *, max_chars: int = 2400) -> str:
    """
    过程稿展示用：优先保留 Markdown 报告段，避免推理流与正文 delta 拼接后的乱码块。
    """
    t = strip_inline_source_markers((text or "").strip())
    if not t:
        return ""
    anchors = (
        "\n### ",
        "\n## ",
        "### ",
        "## ",
        "\n| 项目",
        "\n|项目",
        "\n| ---",
    )
    best_idx = len(t)
    for a in anchors:
        idx = t.find(a)
        if idx != -1 and idx < best_idx:
            best_idx = idx
    if best_idx > 0 and best_idx < len(t) - 40:
        t = t[best_idx:].lstrip()
    if len(t) > max_chars:
        t = t[:max_chars].rstrip() + "…"
    return t


class HermesDraftTraceAccumulator:
    """Hermes Runs 正文 delta 为增量片段；须累积后再 format，勿对单 chunk 格式化。"""

    def __init__(self) -> None:
        self._parts: list[str] = []
        self._last_emitted = ""

    def push(self, chunk: str) -> str | None:
        if chunk:
            self._parts.append(chunk)
        draft = format_hermes_draft_trace("".join(self._parts))
        if not draft or draft == self._last_emitted:
            return None
        self._last_emitted = draft
        return draft

    def flush(self) -> str | None:
        draft = format_hermes_draft_trace("".join(self._parts))
        if not draft or draft == self._last_emitted:
            return None
        self._last_emitted = draft
        return draft


def reply_has_unsupported_estimates(text: str) -> bool:
    return bool(_FORBIDDEN_ESTIMATE.search(text or ""))


def _convert_tsv_tables(text: str) -> str:
    """Hermes 偶发 TSV 表格；转为 Markdown pipe 表以便前端渲染。"""
    t = re.sub(r"([。；;！!?])(\t)", r"\1\n\n", text or "")
    t = re.sub(r"([\u4e00-\u9fff\）\)])(\t(?:项目|指标|科目|职工|销售费用))", r"\1\n\n\2", t)
    lines = t.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if "\t" in line and line.count("\t") >= 2:
            block: list[list[str]] = []
            while i < len(lines):
                ln = lines[i]
                if "\t" not in ln or ln.count("\t") < 2:
                    break
                block.append([c.strip() for c in ln.split("\t")])
                i += 1
            if len(block) >= 2:
                head = block[0]
                out.append("| " + " | ".join(head) + " |")
                out.append("| " + " | ".join("---" for _ in head) + " |")
                for row in block[1:]:
                    cells = row + [""] * max(0, len(head) - len(row))
                    out.append("| " + " | ".join(cells[: len(head)]) + " |")
                continue
        if "\t" in line:
            cells = [c.strip() for c in line.split("\t")]
            if len(cells) >= 3 and cells[0] and not cells[0].startswith("|"):
                out.append(cells[0])
                rest = "\t".join(cells[1:])
                if rest.count("\t") >= 1:
                    lines.insert(i + 1, rest)
                i += 1
                continue
        out.append(line)
        i += 1
    return "\n".join(out)


def _dedupe_report_intro(text: str) -> str:
    """去掉「根据检索到的…以下是…报告」类导语，保留 ### 标题起的正文。"""
    t = (text or "").strip()
    if not t:
        return ""
    m = re.search(r"(#{2,3}\s*华清[^\n]{4,80}(?:对比分析|明细对比)?报告)", t)
    if m and m.start() > 0 and re.search(r"根据检索|以下是", t[: m.start()]):
        return t[m.start() :].strip()
    m2 = re.search(r"(#{2,3}\s*华清[^\n]+)", t)
    if m2 and m2.start() > 80 and "根据检索" in t[:200]:
        return t[m2.start() :].strip()
    return t


def _markdown_structure_score(text: str) -> int:
    s = text or ""
    return (
        s.count("###") * 80
        + s.count("##") * 40
        + len(re.findall(r"\n\|[^\n]+\|", s)) * 15
        + s.count("\n\n") * 5
        + len(s)
    )


def pick_best_hermes_runs_raw(accumulated: str, final_output: str) -> str:
    """Runs API：优先 run_completed 完整 output；否则取结构更完整的累积流。"""
    acc = (accumulated or "").strip()
    fin = (final_output or "").strip()
    if not fin:
        return acc
    if not acc:
        return fin
    if _markdown_structure_score(fin) >= _markdown_structure_score(acc) * 0.85:
        return fin
    if len(fin) >= len(acc) * 0.9:
        return fin
    return acc


def normalize_reply_markdown(text: str) -> str:
    """修复 Hermes 流式挤成一行的标题与 Markdown 表。"""
    t = _dedupe_report_intro((text or "").strip())
    if not t:
        return ""
    t = _convert_tsv_tables(t)
    t = re.sub(r"^(根据检索到的[^\n]+。\n?)", "", t, count=1).strip()
    t = re.sub(
        r"^(华清\s*\d{4}[-、]\d{4}年销售费用[^\n]+报告)\s*$",
        r"## \1",
        t,
        flags=re.M,
    )
    t = re.sub(r"^(结论[：:])", r"## \1", t, flags=re.M)
    t = re.sub(r"([\u4e00-\u9fff\d\-%]+报告)\s*(\d+\.)", r"\1\n\n#### \2", t)
    t = re.sub(r"^(\d+)\.([\u4e00-\u9fff#])", r"#### \1. \2", t, flags=re.M)
    t = re.sub(r"\n(\d+)\.([\u4e00-\u9fff#])", r"\n#### \1. \2", t)
    t = re.sub(r"(\|\s*—\s*\|)\s*(#{2,4})", r"\1\n\n\2", t)
    t = re.sub(r"(\|\s*[^\n]+\|)\s*(#{2,4}\s)", r"\1\n\n\2", t)
    t = re.sub(r"(\n|^)(说明[：:])", r"\1\n### \2", t)
    t = re.sub(r"([。；;！!?])(#{2,4})(\S)", r"\1\n\n\2 \3", t)
    t = re.sub(r"([\u4e00-\u9fff\）\)])(#{2,4})", r"\1\n\n\2", t)
    t = re.sub(r"([\u4e00-\u9fff\）\)])(\|)", r"\1\n\n|", t)
    t = re.sub(r"([。；;！!?％%])(\|)", r"\1\n\n|", t)
    t = re.sub(r"(\|\s*[^\n|]+\|)\s*(说明[：:])", r"\1\n\n\n### \2", t)
    t = re.sub(r"(\|\s*[^\n|]+\|)\s*(\d+\.\s)", r"\1\n\n\n#### \2", t)
    t = re.sub(r"(\|\s*—\s*\|)\s*(\|)", r"\1\n\n\2", t)
    t = re.sub(r"^(#{2,4})([^\s#\d])", r"\1 \2", t, flags=re.M)
    t = re.sub(r"(#{2,4})(\d+\.)", r"\1 \2", t)
    t = re.sub(r"(\*)(#{2,4})", r"\1\n\n\2", t)
    t = re.sub(r"([。；;！!?])(\d+\.\s+)", r"\1\n\n\2", t)
    t = re.sub(r"(\|\s*—\s*\|)\s*(结论)", r"\1\n\n\n### \2", t)
    t = re.sub(r"---+\s*(#{1,4})", r"\n\n\1", t)
    t = re.sub(r"([。；;！!?])(结论[：:])", r"\1\n\n\n**\2**", t)
    t = re.sub(r"([。；;！!?])(引用证据)", r"\1\n\n\n**\2**", t)
    t = re.sub(r"([。；;！!?])(说明[：:])", r"\1\n\n\n**\2**", t)
    lines_out: list[str] = []
    for line in t.split("\n"):
        ln = line
        if ln.count("|") >= 4 and "||" in ln:
            ln = re.sub(r"\|\s*\|", "|\n|", ln)
        lines_out.append(ln)
    t = "\n".join(lines_out)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return strip_inline_source_markers(t.strip())


def finalize_agent_reply(
    reply: str,
    *,
    user_query: str = "",
    tier2_native: bool = False,
) -> str:
    """对比/分解类终稿：剥离过程稿 + 规范化排版；Tier 2 不做本地估算段替换。"""
    body = strip_hermes_orchestration_preamble(extract_user_facing_reply(reply or ""))
    if not body.strip():
        body = (reply or "").strip()
    if tier2_native:
        body = normalize_reply_markdown(body)
        # Tier 2 仍以 Hermes 为终稿来源，但须剔除无证据的「约 xx 万」分项幻觉（不整篇本地重写）
        if reply_has_unsupported_breakdown_amounts(body):
            body = enforce_breakdown_compare_reply(body, user_query=user_query)
        return body
    return enforce_breakdown_compare_reply(body, user_query=user_query)


def _strip_derived_breakdown_sections(text: str) -> str:
    """去掉含反推/计算说明的分项行与注脚；全文出现反推语境时剔除附注表数据行。"""
    from backend.services.evidence_reply_align import reply_has_derived_breakdown_amounts

    if not reply_has_derived_breakdown_amounts(text):
        return text
    lines = (text or "").split("\n")
    out: list[str] = []
    for ln in lines:
        if reply_has_derived_breakdown_amounts(ln):
            continue
        if "|" in ln and re.search(r"\d{1,3}(?:,\d{3})+\.\d{2}", ln):
            if re.match(r"\s*\|[-:\s|]+\|\s*$", ln):
                out.append(ln)
                continue
            if re.search(r"项目|指标|科目|2025|2024|本期|上期", ln):
                out.append(ln)
                continue
            continue
        out.append(ln)
    t = "\n".join(out)
    t = re.sub(
        r"\*\(注：[^*]*计算得出[^*]*\)\*",
        "",
        t,
        flags=re.I,
    )
    if "费用明细说明" not in t and "无法按科目展开" not in t:
        t += (
            "\n\n**说明**：证据中无附注分项明细或存在反推计算；"
            "分项金额须来自引用片段原文，请勿采信反推数值。\n"
        )
    return t.strip()


def enforce_breakdown_compare_reply(reply: str, *, user_query: str = "") -> str:
    """对比/分解类：规范化 Markdown；去掉无证据的「约 xxx 万」明细段。"""
    from backend.services.kb_retrieval_plan import TaskType, infer_task_type

    t = normalize_reply_markdown(reply or "")
    if not t:
        return ""
    tt = infer_task_type(user_query or "")
    if tt not in (TaskType.breakdown, TaskType.compare):
        return t
    if not reply_has_unsupported_breakdown_amounts(t):
        from backend.services.evidence_reply_align import reply_has_contradictory_change_reason

        if reply_has_contradictory_change_reason(t):
            t = re.sub(
                r"证据未提供变动原因说明[^\n]*\n?",
                "",
                t,
            )
        return normalize_reply_markdown(t)
    t = _strip_derived_breakdown_sections(t)
    if reply_has_verifiable_breakdown_table(t):
        t = _strip_unsupported_estimate_prose(t)
        if not reply_has_unsupported_breakdown_amounts(t):
            return normalize_reply_markdown(t)
    sec2 = re.search(r"(#{2,4}\s*2[\.\s、]|#{2,4}\s*费用变动|费用变动分析|\*注：.*\n*#{2,4}\s*2)", t)
    gap = (
        "#### 2. 费用明细说明\n\n"
        "证据中未提供可核查的分项金额，无法按科目展开驱动分析；"
        "若上表已列总额，口径以引用片段为准。\n\n"
    )
    if sec2:
        rest = t[sec2.start() :]
        sec3 = re.search(
            r"(#{2,4}\s*3[\.\s、]|(?:\n|^)\s*3\.\s*结论|#{2,4}\s*结论)",
            rest,
        )
        if sec3:
            t = t[: sec2.start()] + gap + rest[sec3.start() :]
        else:
            t = t[: sec2.start()] + gap
    else:
        t += (
            "\n\n**说明**：证据中无附注分项明细；"
            "正文中「约 xxx 万」等区间描述不符合 Orient-G 证据约束，请勿采信。\n"
        )
    return normalize_reply_markdown(t)


def sanitize_hermes_accumulated_reply(text: str, *, user_query: str = "") -> str:
    body = extract_user_facing_reply(text)
    return enforce_breakdown_compare_reply(body, user_query=user_query)
