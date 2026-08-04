"""人员结构浏览器实测验收规则（横比 / 单主体 / 失败样例）。"""
from __future__ import annotations

import re
from typing import Any

PERSONNEL_COMPARE_QUERY = "对比分析YYCQ和可比公司A25年的人员结构"

BROWSER_FAIL_HERMES_V1 = (
    "结论：证据中缺乏可比公司A2025年的人员结构数据，无法进行对比分析。\n"
    "YYCQ在职员工 139 人；1.1信息-人员 运营 61 研发 70。\n"
    "可比公司A 2025年人员结构数据 缺失证据。\n"
    "YYCQ研发人员数量存在两组数据（95人 vs 1,378人），1,378人数据疑似归属其他主体。"
)

BROWSER_FAIL_HERMES_V2 = (
    "结论：证据严重缺失，无法完成对比分析。\n"
    "完全缺失可比公司A2025年的人员结构数据。\n"
    "研发人员期末为 1,378人，占比43.91%。YYCQ总员工数仅为139人，1,378人显然不可能。\n"
    "1.1信息-人员 研发 70 人。"
)

GOOD_PERSONNEL_COMPARE_EXCERPT = (
    "## YYCQ vs 可比公司A · 2025 人员结构对比\n\n"
    "### 人员结构对照\n\n"
    "| 职能归属 | 可比公司A | YYCQ |\n"
    "| --- | --- | --- |\n"
    "| 研发 | 1378 人（占员工 43.91%） | 70 人 |\n"
    "| 运营 | 242 人 | 61 人 |\n"
    "| 管理 | 36 人 | 33.15 人 |\n"
    "| 支持 | 312 人 | 45.85 人 |\n"
    "| 销售 | 946 人 | 证据未覆盖 |\n\n"
    "### 对比分析\n\n"
    "- **结构差异**：YYCQ为 excel 职能四分项。\n"
)

_PERSONNEL_NOISE = re.compile(
    r"连带责任保证|营业收入合计|营业收入\s*\|\s*15,965",
    re.I,
)

_ENGLISH_PROCESS_LEAK = re.compile(
    r"Let me search|I need to find|The search results confirm|Let's start with these queries",
    re.I,
)

_INCOMPLETE_SANQI_ROW = re.compile(
    r"(?:\|\s*销售\s*\|[^|\n]*证据未覆盖)|(?:\|\s*运营\s*\|[^|\n]*证据未覆盖)|"
    r"(?:^|\n)销售\t[^\t\n]*证据未覆盖|(?:^|\n)运营\t[^\t\n]*证据未覆盖",
    re.M,
)


def personnel_case_kind(query: str) -> str:
    from backend.services.kb_retrieval_plan import (
        extract_query_entity_phrases,
        query_wants_personnel_compare,
        query_wants_personnel_structure,
    )

    q = (query or "").strip()
    if not query_wants_personnel_structure(q):
        return "other"
    if query_wants_personnel_compare(q):
        return "compare"
    ents = extract_query_entity_phrases(q)
    if any("可比公司A" in e for e in ents):
        return "sanqi_single"
    if any(re.search(r"YYCQ", e, re.I) for e in ents):
        return "yycq_single"
    return "personnel_other"


def _entities_in_text(text: str, entities: list[str]) -> dict[str, bool]:
    h = text or ""
    out: dict[str, bool] = {}
    for ent in entities:
        if ent in h:
            out[ent] = True
        elif len(ent) >= 2 and ent[:2] in h:
            out[ent] = True
        else:
            out[ent] = False
    return out


def _probe_amounts_in_text(text: str, kb_probe: dict[str, Any] | None) -> bool:
    if not kb_probe:
        return True
    anchors = kb_probe.get("anchors") or kb_probe.get("amounts") or []
    if not anchors:
        return bool(kb_probe.get("has_data", True))
    hits = sum(1 for a in anchors if str(a) in (text or ""))
    return hits >= 1


def _probe_multi_anchor_ok(text: str, kb_probe: dict[str, Any] | None, *, min_hits: int = 2) -> bool:
    """横比：动态 probe 须命中多个锚点（如 1378 + 70），避免只命中单侧。"""
    if not kb_probe:
        return True
    anchors = [str(a) for a in (kb_probe.get("anchors") or kb_probe.get("amounts") or []) if str(a).strip()]
    if len(anchors) < min_hits:
        return _probe_amounts_in_text(text, kb_probe)
    hits = sum(1 for a in anchors if a in (text or ""))
    return hits >= min(min_hits, len(anchors))


def personnel_compare_sanqi_roles_ok(text: str) -> bool:
    """可比公司A职能分项（销售/运营）已写入对照表或正文。"""
    from backend.services.personnel_compare_report import personnel_compare_sanqi_table_incomplete

    h = text or ""
    if personnel_compare_sanqi_table_incomplete(h):
        return False
    return bool(re.search(r"946", h) and re.search(r"242", h))


def personnel_compare_has_forbidden_leaks(text: str) -> list[str]:
    """返回命中的拒收模式标签。"""
    h = text or ""
    leaks: list[str] = []
    if _ENGLISH_PROCESS_LEAK.search(h):
        leaks.append("english_process_leak")
    # 22.6 倍规模套话仍拒；横比且无对照表时，旁白员工总数视为误归因
    if re.search(r"139人的22\.6倍|22\.6\s*倍", h):
        leaks.append("hermes_misattribution")
    elif (
        re.search(r"可比公司A", h)
        and re.search(r"YYCQ", h)
        and "人员结构对照" not in h
        and re.search(r"员工总数|在职员工总数|一、\s*总体规模|总体规模与", h)
    ):
        leaks.append("hermes_misattribution")
    if "分主体证据摘要" in h:
        leaks.append("excerpt_appendix")
    # 宽尺子 C：推算/推断/约N人/请勿采信掩盖
    if re.search(r"根据推算|(?<![可])推算|可推断|推断|推测为|合理推测", h):
        leaks.append("unsupported_speculation")
    elif re.search(r"约\s*\d{2,6}\s*人", h):
        leaks.append("unsupported_speculation")
    elif re.search(r"请勿采信|勿采信", h) and re.search(r"推断|推算|约\s*\d", h):
        leaks.append("unsupported_speculation")
    return leaks


def validate_personnel_case_spec(
    text: str,
    *,
    spec: dict[str, Any],
    mode: str = "",
    honest: bool = False,
    hermes_kb_ask_calls: int | None = None,
    user_query: str = "",
    reply_source: str | None = None,
    structured_gate_applied: bool | None = None,
    kb_supplemental: bool | None = None,
    gateway_kb_ask_calls: int | None = None,
    hermes_only_kb_ask_calls: int | None = None,
    hermes_mcp_retry_count: int | None = None,
) -> tuple[bool, dict[str, Any]]:
    """按 PERSONNEL_CASE_SPECS 单条期望验收。"""
    checks: dict[str, Any] = {"case_spec": spec.get("angle")}
    must_have = [str(x) for x in (spec.get("must_contain") or []) if str(x).strip()]
    h = text or ""
    if must_have and all(
        needle in h or (needle == "1378" and bool(re.search(r"1[,，]?378", h)))
        for needle in must_have
    ):
        honest = False
        checks["substance_overrides_honest_flag"] = True
    if honest and not must_have:
        checks["honest_ok"] = True
        return True, checks
    if honest and must_have:
        checks["honest_rejected_for_must_contain"] = True
        return False, checks

    leaks = personnel_compare_has_forbidden_leaks(h)
    checks["forbidden_leaks"] = leaks
    if leaks:
        return False, checks

    for needle in spec.get("must_not_contain") or []:
        n = str(needle).strip()
        if not n:
            continue
        if n in h or (n == "推算" and re.search(r"推算|可推断|推断", h)):
            checks[f"must_not_{n}"] = False
            leaks.append("must_not_contain")
            checks["forbidden_leaks"] = leaks
            return False, checks

    # anti-gate 优先：即便内容数字齐全，gate/模板刷绿也必须 FAIL
    if spec.get("require_hermes_authorship"):
        auth_ok, auth_checks = personnel_hermes_authorship_ok(
            h,
            reply_source=reply_source,
            structured_gate_applied=structured_gate_applied,
            kb_supplemental=kb_supplemental,
        )
        checks.update(auth_checks)
        if not auth_ok:
            return False, checks
        from backend.services.kb_ask_mcp_agent_native import (
            is_personnel_mcp_draft_skeleton,
            is_personnel_thin_salvage_final,
        )

        if is_personnel_mcp_draft_skeleton(h) or is_personnel_thin_salvage_final(h):
            checks["hermes_authorship_ok"] = False
            checks["hermes_authorship_fail"] = "thin_mcp_salvage_final"
            return False, checks

    # 目标 4：A3 native 减负 — gateway 上限 + Hermes 自调 MCP 下限（有计数时强制）
    max_gw = spec.get("max_gateway_kb_ask_calls")
    if max_gw is not None and gateway_kb_ask_calls is not None:
        checks["gateway_kb_ask_calls"] = int(gateway_kb_ask_calls)
        checks["max_gateway_kb_ask_calls"] = int(max_gw)
        if int(gateway_kb_ask_calls) > int(max_gw):
            checks["gateway_prefetch_slim_ok"] = False
            return False, checks
        checks["gateway_prefetch_slim_ok"] = True
    min_hermes = spec.get("min_hermes_kb_ask_calls")
    if min_hermes is not None:
        checks["min_hermes_kb_ask_calls"] = int(min_hermes)
        if hermes_only_kb_ask_calls is None:
            # A3/E：缺计数不得刷绿（单次 MCP 够数据 ≠ 充分利用）
            checks["hermes_orientg_kb_ask_calls"] = None
            checks["hermes_mcp_self_ok"] = False
            return False, checks
        checks["hermes_orientg_kb_ask_calls"] = int(hermes_only_kb_ask_calls)
        if int(hermes_only_kb_ask_calls) < int(min_hermes):
            checks["hermes_mcp_self_ok"] = False
            return False, checks
        checks["hermes_mcp_self_ok"] = True

    # 宽尺子 B：强制 MCP 重试不得作为常态（有计数时强制）
    max_retry = spec.get("max_hermes_mcp_retry_count")
    if max_retry is not None and hermes_mcp_retry_count is not None:
        checks["hermes_mcp_retry_count"] = int(hermes_mcp_retry_count)
        checks["max_hermes_mcp_retry_count"] = int(max_retry)
        if int(hermes_mcp_retry_count) > int(max_retry):
            checks["hermes_mcp_retry_ok"] = False
            return False, checks
        checks["hermes_mcp_retry_ok"] = True

    if spec.get("require_sanqi_roles"):
        roles_ok = personnel_compare_sanqi_roles_ok(h)
        checks["sanqi_roles_in_table_ok"] = roles_ok
        if not roles_ok:
            return False, checks

    if spec.get("require_core_table"):
        core_ok = personnel_compare_has_core_table(h)
        checks["personnel_core_table_ok"] = core_ok
        if not core_ok:
            return False, checks

    for needle in spec.get("must_contain") or []:
        key = f"has_{needle}"
        ok = needle in h or (needle == "1378" and bool(re.search(r"1[,，]?378", h)))
        checks[key] = ok
        if not ok:
            return False, checks

    if spec.get("require_analysis"):
        from backend.services.personnel_compare_report import personnel_reply_has_analysis

        analysis_ok = personnel_reply_has_analysis(h)
        checks["personnel_analysis_ok"] = analysis_ok
        if not analysis_ok:
            return False, checks

    if mode == "deep" and spec.get("group") == "A":
        if hermes_kb_ask_calls is None or int(hermes_kb_ask_calls) < 1:
            checks["deep_mcp_required"] = False
            return False, checks
        checks["deep_mcp_required"] = True

    if user_query and spec.get("group") == "A":
        ok, extra = personnel_compare_answer_ok(
            h,
            user_query=user_query,
            mode=mode,
            hermes_kb_ask_calls=hermes_kb_ask_calls if mode == "deep" else None,
        )
        checks.update(extra)
        if (
            not ok
            and spec.get("require_hermes_authorship")
            and checks.get("hermes_authorship_ok")
            and extra.get("misattributed")
            and checks.get("sanqi_roles_in_table_ok")
            and checks.get("has_1378")
        ):
            # Hermes 主写 + 对照表锚点齐全：容忍正文中规模叙事噪声（不为此刷 FAIL）
            checks["misattributed_tolerated_for_hermes_authorship"] = True
            ok = True
        if not ok:
            return False, checks

    checks["personnel_spec_ok"] = True
    return True, checks


def personnel_hermes_authorship_ok(
    text: str,
    *,
    reply_source: str | None = None,
    structured_gate_applied: bool | None = None,
    kb_supplemental: bool | None = None,
) -> tuple[bool, dict[str, Any]]:
    """A3 anti-gate：终稿须可证明 Hermes 主写，禁止 Orient-G 模板指纹/gate 刷绿。"""
    from backend.services.personnel_compare_report import looks_like_orientg_personnel_template

    checks: dict[str, Any] = {}
    template = looks_like_orientg_personnel_template(text)
    checks["orientg_template_fingerprint"] = template
    if template:
        checks["hermes_authorship_ok"] = False
        checks["hermes_authorship_fail"] = "orientg_template_fingerprint"
        return False, checks
    if structured_gate_applied is True:
        checks["structured_gate_applied"] = True
        checks["hermes_authorship_ok"] = False
        checks["hermes_authorship_fail"] = "structured_gate_applied"
        return False, checks
    src = (reply_source or "").strip()
    if src:
        checks["reply_source"] = src
        if src != "hermes":
            checks["hermes_authorship_ok"] = False
            checks["hermes_authorship_fail"] = f"reply_source={src}"
            return False, checks
    if kb_supplemental is True:
        checks["kb_supplemental"] = True
        checks["hermes_authorship_ok"] = False
        checks["hermes_authorship_fail"] = "kb_supplemental"
        return False, checks
    checks["hermes_authorship_ok"] = True
    return True, checks


def personnel_compare_has_core_table(text: str) -> bool:
    h = (text or "").strip()
    if not re.search(r"人员结构对照", h):
        return False
    role = r"(运营|管理|支持|研发|销售)(?:人员)?"
    # markdown 管道表（Hermes 常写「研发人员」）；第三列可为人数或「证据未覆盖」
    pipe_rows = len(
        re.findall(rf"\|\s*{role}\s*\|[^|\n]*\|\s*(?:[\d—]|证据未覆盖|—|-)", h)
    )
    if pipe_rows >= 3:
        return True
    # DOM prose 渲染常为制表符分隔
    tab_rows = len(re.findall(rf"(?:^|\n){role}\t[^\t\n]+\t", h, re.M))
    return tab_rows >= 3


def personnel_compare_answer_ok(
    text: str,
    *,
    honest: bool = False,
    user_query: str = "",
    kb_probe: dict[str, Any] | None = None,
    mode: str = "standard",
    hermes_kb_ask_calls: int | None = None,
) -> tuple[bool, dict[str, Any]]:
    from backend.services.kb_ask_mcp_reply import personnel_compare_reply_misattributed
    from backend.services.kb_retrieval_plan import extract_query_entity_phrases
    from backend.services.personnel_compare_report import (
        personnel_excerpt_dump_only,
        personnel_reply_has_analysis,
    )

    uq = user_query or PERSONNEL_COMPARE_QUERY
    checks: dict[str, Any] = {}

    if personnel_compare_reply_misattributed(text, user_query=uq):
        checks["misattributed"] = True
        return False, checks

    leaks = personnel_compare_has_forbidden_leaks(text or "")
    if leaks:
        checks["forbidden_leaks"] = leaks
        return False, checks

    if honest:
        checks["honest_ok"] = True
        return True, checks

    if _PERSONNEL_NOISE.search(text or ""):
        checks["noise"] = True
        return False, checks

    entities = extract_query_entity_phrases(uq)
    checks["entities"] = entities
    ent_hits = _entities_in_text(text, entities)
    checks["entity_present"] = ent_hits
    if len(entities) >= 2 and not all(ent_hits.values()):
        return False, checks

    if not re.search(r"研发人员|1\.1信息-人员|人员结构|在职员工", text or "", re.I):
        checks["personnel_topic"] = False
        return False, checks

    if personnel_excerpt_dump_only(text):
        checks["excerpt_dump_only"] = True
        return False, checks

    if "分主体证据摘要" in (text or ""):
        checks["has_excerpt_appendix"] = True
        return False, checks

    kb_ok = _probe_amounts_in_text(text, kb_probe)
    checks["kb_probe_match"] = kb_ok
    if kb_probe and not kb_ok:
        return False, checks

    if mode in ("deep", "standard", "fast"):
        core_ok = personnel_compare_has_core_table(text)
        checks["personnel_core_table_ok"] = core_ok
        if not core_ok:
            return False, checks
        # YYCQ excel 分项：对照表研发人数不得为 1 等明显误解析（应为 70 量级）
        if re.search(r"YYCQ", text or "") and re.search(
            r"\|\s*研发\s*\|[^|\n]*\|\s*1\s*人\s*\|", text or "", re.I
        ):
            checks["yycq_rd_parse_ok"] = False
            return False, checks
        if re.search(r"excel[^.\n]{0,40}研发[^.\n]{0,20}约\s*1\s*人", text or "", re.I):
            checks["yycq_rd_parse_ok"] = False
            return False, checks
        from backend.services.personnel_compare_report import personnel_compare_sanqi_table_incomplete

        sanqi_incomplete = personnel_compare_sanqi_table_incomplete(text or "")
        checks["sanqi_roles_in_table_ok"] = not sanqi_incomplete
        if sanqi_incomplete:
            return False, checks

    if mode == "deep":
        checks["orientg_kb_ask_calls"] = hermes_kb_ask_calls
        if hermes_kb_ask_calls is None:
            checks["deep_mcp_required"] = False
            return False, checks
        total_kb = int(hermes_kb_ask_calls)
        if total_kb < 1 and personnel_compare_has_core_table(text):
            if _probe_multi_anchor_ok(text, kb_probe, min_hits=2):
                total_kb = 1
                checks["deep_mcp_inferred_from_structured"] = True
        if total_kb < 1:
            checks["deep_mcp_required"] = False
            return False, checks
        multi_ok = _probe_multi_anchor_ok(text, kb_probe, min_hits=2)
        checks["kb_probe_multi_anchor"] = multi_ok
        if kb_probe and not multi_ok:
            return False, checks
        analysis_ok = personnel_reply_has_analysis(text)
        checks["personnel_analysis_ok"] = analysis_ok
        if not analysis_ok:
            return False, checks

    checks["personnel_compare_ok"] = True
    return True, checks


def personnel_single_answer_ok(text: str, *, kind: str, honest: bool = False, user_query: str = "") -> bool:
    from backend.services.kb_retrieval_plan import extract_query_entity_phrases

    if honest:
        return True
    h = text or ""
    ents = extract_query_entity_phrases(user_query) if user_query else []
    if kind == "sanqi_single":
        if ents and not any(e in h or "可比公司A" in h for e in ents):
            return False
        return bool(re.search(r"研发人员|研发人员数量|研发人员情况|\d{3,4}", h))
    if kind == "yycq_single":
        if ents and not any(re.search(r"YYCQ", e, re.I) for e in ents):
            return False
        return bool(re.search(r"1\.1信息-人员|研发|\d+\.\d{2}", h))
    return len(h) >= 80


def augment_validate_row_personnel(
    row: dict[str, Any],
    answer_text: str,
    *,
    honest: bool,
    kb_probe: dict[str, Any] | None = None,
) -> tuple[bool, dict[str, Any]]:
    """供 finance_matrix_browser_validate.validate_row 调用。"""
    uq = str(row.get("query") or "")
    kind = personnel_case_kind(uq)
    mode = str(row.get("mode") or "")
    checks: dict[str, Any] = {"personnel_case_kind": kind}

    stats = row.get("hermes_stream_stats") or {}
    hermes_kb = stats.get("hermes_orientg_kb_ask_calls")
    gateway_kb = stats.get("gateway_orientg_kb_ask_calls")
    orientg_kb = stats.get("orientg_kb_ask_calls")
    retry_count = stats.get("hermes_mcp_retry_count")
    if hermes_kb is None and row.get("hermes_kb_ask_calls") is not None:
        hermes_kb = row.get("hermes_kb_ask_calls")
    if gateway_kb is None and row.get("gateway_kb_ask_calls") is not None:
        gateway_kb = row.get("gateway_kb_ask_calls")
    if orientg_kb is None and row.get("orientg_kb_ask_calls") is not None:
        orientg_kb = row.get("orientg_kb_ask_calls")
    if retry_count is None and row.get("hermes_mcp_retry_count") is not None:
        retry_count = row.get("hermes_mcp_retry_count")
    if hermes_kb is None or retry_count is None:
        blob = (
            str(row.get("tier_line") or "")
            + str(row.get("notes") or "")
            + str((row.get("extract") or {}).get("body_sample") or "")
            + str((row.get("extract") or {}).get("head") or "")
        )
        if hermes_kb is None:
            m = re.search(r"Hermes 内 orientg_kb_ask ×(\d+)", blob)
            if m:
                hermes_kb = int(m.group(1))
            mg = re.search(r"(?:网关 orientg_kb_ask|Orient-G 网关 KB)\s*×(\d+)", blob)
            if mg:
                gateway_kb = int(mg.group(1))
            prefetch_hits = len(re.findall(r"预检索：orientg_kb_ask", blob))
            if prefetch_hits > 0:
                gateway_kb = max(int(gateway_kb or 0), prefetch_hits)
        if retry_count is None:
            if re.search(r"MCP 优先重试|hermes_mcp_retry", blob, re.I):
                retry_count = 1
            mr = re.search(r"hermes_mcp_retry(?:_count)?\s*[:=]\s*(\d+)", blob, re.I)
            if mr:
                retry_count = int(mr.group(1))
    total_kb = int(orientg_kb or 0)
    if total_kb < 1:
        total_kb = int(hermes_kb or 0) + int(gateway_kb or 0)

    from finance_matrix_personnel_cases import personnel_case_spec_for_row

    reply_source = row.get("reply_source")
    if reply_source is None:
        blob = (
            str(row.get("tier_line") or "")
            + str(row.get("notes") or "")
            + str((row.get("extract") or {}).get("body_sample") or "")
        )
        m_src = re.search(r"终稿出处[：:]\s*([A-Za-z_\u4e00-\u9fff]+)", blob)
        if m_src:
            label = m_src.group(1).strip()
            reply_source = {
                "Hermes": "hermes",
                "hermes": "hermes",
                "Orient-G门禁": "orientg_structured_gate",
                "structured_gate": "orientg_structured_gate",
            }.get(label, label if label in ("hermes", "orientg_structured_gate") else None)
    structured_gate_applied = row.get("structured_gate_applied")
    if structured_gate_applied is None and re.search(
        r"structured_gate_applied\s*[:=]\s*true|终稿出处[：:].*gate",
        str(row.get("tier_line") or "") + str(row.get("notes") or ""),
        re.I,
    ):
        structured_gate_applied = True
    kb_supplemental = row.get("kb_supplemental")
    if kb_supplemental is None and re.search(
        r"Orient-G 自动补检索修订|kb_supplemental\s*[:=]\s*true",
        str(row.get("tier_line") or "") + str(row.get("notes") or ""),
        re.I,
    ):
        kb_supplemental = True

    spec = personnel_case_spec_for_row(row)
    if spec:
        ok, extra = validate_personnel_case_spec(
            answer_text,
            spec=spec,
            mode=mode,
            honest=honest,
            hermes_kb_ask_calls=total_kb if mode == "deep" else None,
            user_query=uq,
            reply_source=str(reply_source) if reply_source is not None else None,
            structured_gate_applied=(
                bool(structured_gate_applied) if structured_gate_applied is not None else None
            ),
            kb_supplemental=bool(kb_supplemental) if kb_supplemental is not None else None,
            gateway_kb_ask_calls=int(gateway_kb) if gateway_kb is not None else None,
            hermes_only_kb_ask_calls=int(hermes_kb) if hermes_kb is not None else None,
            hermes_mcp_retry_count=int(retry_count) if retry_count is not None else None,
        )
        checks.update(extra)
        checks["personnel_case_kind"] = kind
        checks["personnel_subject"] = row.get("subject")
        return ok, checks

    if kind == "compare":
        ok, extra = personnel_compare_answer_ok(
            answer_text,
            honest=honest,
            user_query=uq,
            kb_probe=kb_probe,
            mode=mode,
            hermes_kb_ask_calls=total_kb if mode == "deep" else None,
        )
        checks.update(extra)
        return ok, checks
    if kind in ("sanqi_single", "yycq_single"):
        ok = personnel_single_answer_ok(answer_text, kind=kind, honest=honest, user_query=uq)
        checks["personnel_single_ok"] = ok
        return ok, checks
    checks["personnel_compare_ok"] = True
    return True, checks
