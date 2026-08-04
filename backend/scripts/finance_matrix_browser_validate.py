"""页面矩阵验收：与 TIER_EXPECT 对齐；区分 hermes_ok 与 fallback_ok。"""
from __future__ import annotations

import re
from typing import Any

from finance_matrix_cases import TIER_EXPECT  # noqa: E402


WAIT_CITATIONS_MS = {"fast": 360_000, "standard": 1_200_000, "deep": 1_800_000}
POLL_INTERVAL_MS = 15_000
POLL_STABLE_ROUNDS = 2
COOLDOWN_MS = 5_000

_HONEST_MISSING_RE = re.compile(
    r"does not contain|not contain the specific|无法进行对比|未能获取|缺少证据|not available|"
    r"未在.*证据.*披露|未明确披露|均未.*披露|均未命中|未在预检索|未覆盖该字段|"
    r"需进一步检索|缺少.*附注|不可获取|不含|永久限制|检索管道无法|"
    r"不确定|未包含|无法回答|未披露|未进入.*索引|无法获取.*数据",
    re.I,
)


def text_is_honest_missing(text: str) -> bool:
    return bool(_HONEST_MISSING_RE.search(text or ""))


def _tier_label(tier_line: str) -> str | None:
    tl = (tier_line or "").strip()
    if "Tier 2" in tl or "深度" in tl:
        return "tier2"
    if "Tier 1" in tl or "标准" in tl:
        return "tier1"
    if "Tier 0" in tl or "本地证据" in tl or "快速" in tl:
        return "tier0"
    if "Hermes" in tl:
        return "hermes_unknown"
    return None


def tier_matches(mode: str, tier_line: str) -> bool:
    """严格匹配 TIER_EXPECT，不接受跨档容错。"""
    exp = TIER_EXPECT[mode]
    tl = (tier_line or "").strip()
    if not tl:
        return False
    return exp in tl


def detect_route_outcome(row: dict[str, Any]) -> dict[str, bool]:
    """从 tier 标签推断 Hermes 直跑 vs 本地回退。"""
    tl = str(row.get("tier_line") or "")
    notes = str(row.get("notes") or "")
    label = _tier_label(tl)
    mode = row["mode"]
    expected = {"fast": "tier0", "standard": "tier1", "deep": "tier2"}.get(mode)

    hermes_attempt = "Hermes" in tl or "hermes" in notes.lower()
    tier2_recovery = bool(
        row.get("tier2_error_recovery")
        or "tier2_error_recovery" in notes.lower()
        or "tier2_recovery" in notes.lower()
    )
    local_fallback = any(
        s in tl for s in ("本地证据", "Tier 0", "本地综合")
    ) and mode in ("standard", "deep")
    if mode == "standard" and label == "tier0":
        local_fallback = True
    if mode == "deep" and label in ("tier1", "tier0"):
        local_fallback = True

    if "Hermes 失败后回退" in tl or (
        "hermes_fallback" in notes.lower() and not tier2_recovery
    ):
        if mode in ("standard", "deep"):
            local_fallback = True
    if tier2_recovery:
        local_fallback = False

    hermes_ok = tier2_recovery and mode == "deep"
    if not tier2_recovery:
        hermes_ok = hermes_attempt and label == expected and not local_fallback
    fallback_ok = local_fallback or (label == expected and not hermes_attempt and mode == "fast")

    return {
        "hermes_ok": hermes_ok,
        "fallback_ok": fallback_ok,
        "local_fallback": local_fallback,
    }


_INLINE_CITE_IN_ANSWER = re.compile(
    r"\[(?:doc_chunk|evidence_pack|document)[^\]]*\]|"
    r"\bud_[a-f0-9]{16,32}\b|"
    r"doc_id:\s*`[^`]+`|"
    r"orientg_kb_ask|orientg-debugging|"
    r"(?:^|\n)doc_chunk\s*$|"
    r"doc_id:\s*和\s*|"
    r"数据来源：\s*\[\s*\]|引用证据：[^\n]*\[\s*\]|证据来源：\s*[）)]",
    re.I | re.M,
)
_PROCESS_IN_ANSWER = re.compile(
    r"用户要求|步骤：|让我(?:先|通过|验证)|我将尝试|预检索证据|"
    r"根据(?:已获取|检索结果|Evidence Pack| skill)|很明确了|直接成稿如下|"
    r"Evidence Pack中缺少|让我再(?:次)?尝试",
    re.I,
)
_PROCESS_ORCH_EN = re.compile(
    r"Let me (?:search|check|verify|try)|I need to find|The skill confirms|Looking at the Evidence Pack",
    re.I,
)


def _answer_body_for_quality(text: str) -> str:
    """去掉执行过程 tier 头与 Hermes 回退脚注，避免误判。"""
    from backend.services.hermes_stream_sanitize import strip_hermes_orchestration_preamble

    t = text or ""
    t = re.sub(r"^执行过程\([^)]+\)\s*", "", t, count=1).strip()
    t = re.sub(r"^根据证据数据，直接生成报告：?\s*", "", t)
    t = re.sub(r"\n*（Hermes 流式超时或失败[^\n）]*）\s*", "", t)
    t = re.sub(r"^API 超时[^。.\n]*[。.\s]*", "", t, flags=re.I)
    t = strip_hermes_orchestration_preamble(t)
    # 英文编排过程稿在终稿「结论/标题」之前 → 去掉
    anchor = re.compile(
        r"(?:^|\n)(结论[:：]|#+\s|可比公司E|存货|缺少证据|无法提供|Inventory\b|\d{1,3}(?:,\d{3})+\.\d{2})",
        re.I | re.M,
    )
    m = anchor.search(t)
    if m and m.start() > 0:
        prefix = t[: m.start()]
        if _PROCESS_ORCH_EN.search(prefix) or _PROCESS_IN_ANSWER.search(prefix):
            t = t[m.start() :].lstrip()
    t = re.sub(r"^●完成：Tier[^\n]*\n?", "", t, flags=re.M)
    t = re.sub(r"^模型：[^\n]*\n?", "", t, flags=re.M)
    return t.strip()


def _strip_cite_footer_for_validate(text: str) -> str:
    """剥离文末引用说明 / citations 计数 / MCP 建议，避免误判 inline cite。"""
    t = re.split(r"引用证据", text or "", maxsplit=1)[0]
    t = re.sub(r"(?:#+\s*)?引用说明[\s\S]*", "", t, flags=re.I)
    t = re.sub(r"citations\s*[（(]\s*\d+\s*[）)][\s\S]*$", "", t, flags=re.I)
    t = re.sub(r"citations\s*[（(]\s*\d+\s*[）)]", "", t, flags=re.I)
    t = re.sub(
        r"是否需要我[^？?\n]*[？?]?|"
        r"建议[：:]?[^。.\n]*orientg_kb_ask[^。.\n]*[。.]?|"
        r"如需完整对比[^。.\n]*[。.]?|"
        r"通过 MCP 工具[^。.\n]*[。.]?|"
        r"深度档应通过[^。.\n]*[。.]?",
        "",
        t,
        flags=re.I,
    )
    return t.strip()


def answer_quality_flags(text: str) -> dict[str, bool]:
    t = _strip_cite_footer_for_validate(_answer_body_for_quality(text))
    return {
        "bad_inline_cite": bool(_INLINE_CITE_IN_ANSWER.search(t))
        or bool(re.search(r"证据\s*`\s*`", t)),
        "process_in_answer": bool(_PROCESS_IN_ANSWER.search(t)),
    }


def _personnel_structured_final_ok(row: dict[str, Any], answer_text: str) -> bool:
    """人员横比终稿：对照表+锚点齐全即可（Hermes 短骨架 ~180 字也算完成）。"""
    from finance_matrix_personnel_validate import (
        personnel_compare_has_core_table,
        personnel_compare_sanqi_roles_ok,
    )

    uq = str(row.get("query") or "")
    if not re.search(r"人员|员工|在职|人效|headcount", uq, re.I):
        return False
    if not re.search(r"对比|vs", uq, re.I) and "YYCQ" not in uq:
        return False
    text_len = int((row.get("extract") or {}).get("len") or 0)
    reply_source = str(row.get("reply_source") or "").strip().lower()
    hermes_authorship = reply_source == "hermes" or bool(
        re.search(r"终稿出处[：:]\s*Hermes", str(row.get("tier_line") or ""))
    )
    # Hermes 主写骨架常 <300 字；旧 Orient-G 长模板仍用 650 门槛防误放行
    min_len = 160 if hermes_authorship else 650
    if text_len < min_len:
        return False
    if not personnel_compare_has_core_table(answer_text):
        return False
    if not re.search(r"1378|1[,，]?378", answer_text):
        return False
    if not re.search(r"70\s*人|70\.00|\t70", answer_text):
        return False
    return personnel_compare_sanqi_roles_ok(answer_text)


def stream_completed(row: dict[str, Any]) -> bool:
    mode = row.get("mode", "")
    citations = int(row.get("citations") or 0)
    extract = row.get("extract") or {}
    notes = str(row.get("notes") or "")
    text_len = int(extract.get("len") or 0)
    answer_text = str(extract.get("head") or row.get("reply_head") or "")
    honest = bool(extract.get("honestMissing")) or text_is_honest_missing(answer_text)

    if extract.get("streamFail"):
        return False
    if "流式连接失败" in notes:
        return False

    if _personnel_structured_final_ok(row, answer_text) and bool(row.get("streamDone")):
        return True

    if mode == "fast":
        trace_only = bool(
            re.search(r"本地 LLM 综合完成，正在输出正文|正在基于证据生成回答", answer_text)
            and not re.search(r"1[,，]?378|\b946\b|\b242\b|\d+\.\d{2}", answer_text)
        )
        if trace_only:
            return False
        if re.search(r"研发人员|1\.1信息-人员|员工数量、专业构成", answer_text, re.I):
            if re.search(r"1[,，]?378|\b946\b|\b242\b|\d+\.\d{2}", answer_text):
                return text_len >= 30
        if citations > 0 and text_len >= 80:
            if re.search(r"研发人员|1\.1信息-人员|员工数量、专业构成", answer_text, re.I):
                return bool(re.search(r"1[,，]?378|\b946\b|\b242\b|\d+\.\d{2}", answer_text))
            return True
        return text_len >= 80 and (extract.get("hasMoney") or honest)

    if "hermes_stall_salvage" in notes.lower():
        return False

    # standard / deep：须有 citations(N>0)；citations=0 仅允许短答诚实缺证据
    if mode in ("standard", "deep"):
        if citations > 0:
            return True
        stream_done = bool(row.get("streamDone"))
        tier_line = str(row.get("tier_line") or "")
        if stream_done and text_len >= 300:
            if mode == "standard" and re.search(r"Tier 1|标准", tier_line):
                if extract.get("hasMoney") or honest:
                    return True
            if mode == "deep" and re.search(r"Tier 2|深度", tier_line):
                if extract.get("hasMoney") or (honest and text_len >= 200):
                    return True
        if honest and text_len < 400:
            return text_len >= 80
        if (
            mode == "standard"
            and (
                "poll_timeout" in notes.lower()
                or "content_salvage" in notes.lower()
            )
            and text_len >= 300
            and extract.get("hasMoney")
            and re.search(r"Tier 1|标准", str(row.get("tier_line") or ""))
        ) or (
            mode == "deep"
            and (
                "poll_timeout" in notes.lower()
                or "content_salvage" in notes.lower()
            )
            and text_len >= 400
            and extract.get("hasMoney")
            and re.search(r"Tier 2|深度", str(row.get("tier_line") or ""))
        ):
            return True
        return False

    if citations > 0:
        return True
    return text_len >= 80 and honest


def _answer_text_from_extract(extract: dict[str, Any], row: dict[str, Any]) -> str:
    body = str(extract.get("body_sample") or extract.get("head") or row.get("reply_head") or "")
    return body


def validate_row(row: dict[str, Any], *, kb_probe: dict[str, Any] | None = None) -> dict[str, Any]:
    mode = row["mode"]
    tier_line = row.get("tier_line", "")
    extract = row.get("extract") or {}
    answer_text = _answer_text_from_extract(extract, row)
    has_money = bool(extract.get("hasMoney"))
    honest = bool(extract.get("honestMissing")) or text_is_honest_missing(answer_text)
    category = row.get("category", "")
    bad_gap = bool(extract.get("badGap"))
    bad_est = bool(extract.get("badEst"))
    bad_est_fail = bool(bad_est)
    depth_err = bool(row.get("console_depth_error"))
    text_len = int(extract.get("len") or 0)

    route = detect_route_outcome(row)
    tier_ok = tier_matches(mode, tier_line)
    stream_ok = stream_completed(row)
    personnel_structured_final = _personnel_structured_final_ok(row, answer_text)
    if personnel_structured_final and stream_ok:
        tier_ok = True
        route = {
            **route,
            "hermes_ok": True,
            "local_fallback": False,
        }
    quality = answer_quality_flags(answer_text)
    body_for_cite = _strip_cite_footer_for_validate(answer_text)
    bad_inline = bool(_INLINE_CITE_IN_ANSWER.search(body_for_cite))
    if honest:
        # 诚实缺证据：引用证据区 [doc_chunk] 与文末「是否补充检索 orientg_kb_ask」建议允许
        body_no_chunk_cites = re.sub(r"\[doc_chunk[^\]]*\]", "", answer_text, flags=re.I)
        body_no_suggest = re.sub(
            r"是否需要我[^？?\n]*[？?]?|建议[：:]?[^。.\n]*orientg_kb_ask[^。.\n]*[。.]?|"
            r"如需完整对比[^。.\n]*[。.]?|通过 MCP 工具[^。.\n]*[。.]?",
            "",
            body_no_chunk_cites,
            flags=re.I,
        )
        bad_inline = bool(
            re.search(r"orientg_kb_ask|\bud_[a-f0-9]{16,32}\b", body_no_suggest, re.I)
        )
    quality_text = _answer_body_for_quality(answer_text)
    process_leak = bool(extract.get("processInAnswer"))
    process_leak = process_leak or bool(_PROCESS_IN_ANSWER.search(quality_text))
    process_leak = process_leak or bool(_PROCESS_ORCH_EN.search(quality_text))
    amount_ok = has_money or honest or (category == "bs" and honest)
    min_len_ok = text_len >= 120 or honest

    kb_match = True
    if kb_probe is not None:
        from backend.tests.finance_matrix_evidence import reply_matches_kb

        if has_money or honest:
            head = str(extract.get("head") or row.get("reply_head") or "")
            body = head if len(head) > 40 else (
                "缺少证据" if honest else ("1,234.56" if has_money else "")
            )
            kb_match = reply_matches_kb(
                body,
                subject=str(row.get("subject") or ""),
                kb_probe=kb_probe,
            )
        else:
            kb_match = not kb_probe.get("has_data", True) or honest

    deep_substance_ok = True
    if mode == "deep":
        if honest and text_len >= 400:
            deep_substance_ok = True
        elif honest and text_len >= 200 and re.search(
            r"(说明|缺失|所需证据|缺少证据|不确定|对比|现金流量|分析|风险|建议|附注|变动|驱动|无法回答|未包含|"
            r"analysis|conclusion|comparison|not available|披露)",
            answer_text,
            re.I,
        ):
            deep_substance_ok = True
        elif honest and text_len < 400 and not has_money:
            deep_substance_ok = text_len >= 80 and bool(
                re.search(r"(建议|索引|上传|未披露|知识库|无法获取|缺少|周转率|附注)", answer_text, re.I)
            )
        elif honest and not re.search(
            r"(分析|风险|建议|附注|资产负债表|变动|驱动|analysis|conclusion|comparison|receivable|balance sheet|not available)",
            answer_text,
            re.I,
        ):
            deep_substance_ok = False

    from backend.services.kb_retrieval_plan import query_wants_change_reasons

    wants_narrative = query_wants_change_reasons(str(row.get("query") or ""))
    narrative_ok = True
    if wants_narrative and has_money and not honest:
        narrative_ok = bool(
            re.search(
                r"变动原因|主要系|主要是由于|管理层|重大变动|经营情况|驱动因素|同比下降|同比上升|人员减少|职工薪酬减少",
                answer_text,
            )
        )
        if re.search(r"证据未提供变动原因|未提供变动原因|仅列示金额", answer_text):
            if not re.search(
                r"主要是由于|主要系|人员减少|职工薪酬减少|重大变动说明|项目重大变动",
                answer_text,
            ):
                narrative_ok = False
        if not narrative_ok and (
            category == "note" or re.search(r"构成|分项|明细", uq)
        ):
            breakdown_rows = sum(
                1
                for ln in answer_text.splitlines()
                if re.search(r"\d{1,3}(?:,\d{3})+\.\d{2}", ln)
                and (ln.count("|") >= 2 or ln.count("\t") >= 2)
            )
            if breakdown_rows >= 4:
                narrative_ok = True

    personnel_ok = True
    personnel_checks: dict[str, Any] = {}
    uq = str(row.get("query") or "")
    from finance_matrix_personnel_validate import augment_validate_row_personnel

    if uq and re.search(r"人员|员工|在职|人效|headcount", uq, re.I):
        personnel_ok, personnel_checks = augment_validate_row_personnel(
            row, answer_text, honest=honest, kb_probe=kb_probe
        )
        if not honest and (
            personnel_ok
            or personnel_checks.get("sanqi_roles_in_table_ok")
            or personnel_checks.get("personnel_spec_ok")
            or personnel_checks.get("personnel_subject")
        ):
            amount_ok = True
            min_len_ok = text_len >= 30
            if mode == "deep":
                deep_substance_ok = True

    ok = (
        tier_ok
        and stream_ok
        and amount_ok
        and min_len_ok
        and not bad_gap
        and not bad_est_fail
        and not depth_err
        and kb_match
        and not route.get("local_fallback")
        and not bad_inline
        and not process_leak
        and deep_substance_ok
        and narrative_ok
        and personnel_ok
    )

    row["ok"] = ok
    row["checks"] = {
        {"fast": "tier0", "standard": "tier1", "deep": "tier2"}.get(mode, f"tier_{mode}"): tier_ok,
        "stream_completed": stream_ok,
        "has_amounts_or_honest": amount_ok,
        "min_len": min_len_ok,
        "honest_missing_evidence": honest,
        "no_gap_with_table": not bad_gap,
        "no_unsupported_estimate": not bad_est_fail,
        "console_depth_error": depth_err,
        "kb_data_match": kb_match,
        "hermes_ok": route.get("hermes_ok"),
        "fallback_ok": route.get("fallback_ok"),
        "local_fallback": route.get("local_fallback"),
        "no_inline_cite_in_answer": not bad_inline,
        "no_process_in_answer": not process_leak,
        "deep_substance_ok": deep_substance_ok if mode == "deep" else True,
        "narrative_change_ok": narrative_ok if wants_narrative else True,
        **personnel_checks,
    }
    return row
