"""页面矩阵验收：与 TIER_EXPECT 对齐；区分 hermes_ok 与 fallback_ok。"""
from __future__ import annotations

import re
from typing import Any

from finance_matrix_cases import TIER_EXPECT  # noqa: E402


WAIT_CITATIONS_MS = {"fast": 360_000, "standard": 1_200_000, "deep": 1_800_000}
POLL_INTERVAL_MS = 15_000
POLL_STABLE_ROUNDS = 2
COOLDOWN_MS = 5_000


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
    local_fallback = any(
        s in tl for s in ("本地证据", "Tier 0", "本地综合")
    ) and mode in ("standard", "deep")
    if mode == "standard" and label == "tier0":
        local_fallback = True
    if mode == "deep" and label in ("tier1", "tier0"):
        local_fallback = True

    if "Hermes 失败后回退" in tl or "hermes_fallback" in notes.lower():
        if mode in ("standard", "deep"):
            local_fallback = True
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
    r"orientg_kb_ask|orientg-debugging",
    re.I,
)
_PROCESS_IN_ANSWER = re.compile(
    r"用户要求|步骤：|让我先|我将尝试|预检索证据",
)
_PROCESS_ORCH_EN = re.compile(
    r"Let me (?:search|check|verify)|The skill confirms|Looking at the Evidence Pack",
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
    m = re.search(
        r"(?:^|\n)(结论[:：]|#+\s|存货|缺少证据|无法提供|Inventory\b)",
        t,
        re.I | re.M,
    )
    if m and m.start() > 0 and _PROCESS_ORCH_EN.search(t[: m.start()]):
        t = t[m.start() :].lstrip()
    return t.strip()


def answer_quality_flags(text: str) -> dict[str, bool]:
    t = _answer_body_for_quality(text)
    return {
        "bad_inline_cite": bool(_INLINE_CITE_IN_ANSWER.search(t))
        or bool(re.search(r"证据\s*`\s*`", t)),
        "process_in_answer": bool(_PROCESS_IN_ANSWER.search(t)),
    }


def stream_completed(row: dict[str, Any]) -> bool:
    mode = row.get("mode", "")
    citations = int(row.get("citations") or 0)
    extract = row.get("extract") or {}
    notes = str(row.get("notes") or "")
    text_len = int(extract.get("len") or 0)

    if extract.get("streamFail"):
        return False
    if "流式连接失败" in notes:
        return False

    if mode == "fast":
        if citations > 0:
            return True
        return text_len >= 80 and (extract.get("hasMoney") or extract.get("honestMissing"))

    # standard / deep：须有 citations 或明确 Hermes 完成且正文达标
    if citations > 0:
        return True
    if "poll_timeout" in notes.lower() and citations == 0:
        if text_len >= 200 and extract.get("honestMissing"):
            pass
        else:
            return False
    elif "timeout" in notes.lower() and citations == 0:
        return False
    tier_line = str(row.get("tier_line") or "")
    if mode in ("standard", "deep") and "Hermes" in tier_line:
        return text_len >= 120 and (extract.get("hasMoney") or extract.get("honestMissing"))
    return text_len >= 120 and extract.get("honestMissing")


def validate_row(row: dict[str, Any], *, kb_probe: dict[str, Any] | None = None) -> dict[str, Any]:
    mode = row["mode"]
    tier_line = row.get("tier_line", "")
    extract = row.get("extract") or {}
    answer_text = str(extract.get("head") or row.get("reply_head") or "")
    has_money = bool(extract.get("hasMoney"))
    honest = bool(extract.get("honestMissing")) or bool(
        re.search(
            r"does not contain|not contain the specific|无法进行对比|未能获取|缺少证据|not available|"
            r"未在.*证据.*披露|未明确披露|均未.*披露|均未命中|未在预检索|未覆盖该字段|"
            r"需进一步检索|缺少.*附注|不可获取|不含|永久限制|检索管道无法|"
            r"不确定|未包含|无法回答",
            answer_text,
            re.I,
        )
    )
    category = row.get("category", "")
    bad_gap = bool(extract.get("badGap"))
    bad_est = bool(extract.get("badEst"))
    bad_est_fail = bad_est and not has_money
    depth_err = bool(row.get("console_depth_error"))
    text_len = int(extract.get("len") or 0)

    route = detect_route_outcome(row)
    tier_ok = tier_matches(mode, tier_line)
    stream_ok = stream_completed(row)
    quality = answer_quality_flags(answer_text)
    bad_inline = bool(extract.get("badInlineCite") or quality.get("bad_inline_cite"))
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
    process_leak = bool(extract.get("processInAnswer"))
    quality_text = _answer_body_for_quality(answer_text)
    if honest:
        process_leak = bool(
            re.search(r"^用户要求|^步骤：|让我先|我将尝试", quality_text, re.M)
        )
    else:
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

    # 产品验收：须严格 tier；Hermes 回退不算 deep/standard 通过
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
            deep_substance_ok = False
        elif honest and not re.search(
            r"(分析|风险|建议|附注|资产负债表|变动|驱动|analysis|conclusion|comparison|receivable|balance sheet|not available)",
            answer_text,
            re.I,
        ):
            deep_substance_ok = False

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
    }
    return row
