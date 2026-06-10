"""加载 skill.finance.annual_report.v1 的 disclosure / retrieval profile（供预检索与 Agent 路由）。"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

_SKILL_ID = "skill.finance.annual_report.v1"


def _skills_root() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "agent_skills"


def _skill_refs_dir(skill_id: str = _SKILL_ID) -> Path:
    return _skills_root() / skill_id / "references"


def _load_json(name: str, *, skill_id: str = _SKILL_ID) -> dict[str, Any]:
    import json

    path = _skill_refs_dir(skill_id) / name
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


@lru_cache(maxsize=4)
def load_disclosure_regimes(*, skill_id: str = _SKILL_ID) -> dict[str, Any]:
    return _load_json("disclosure_regimes.json", skill_id=skill_id)


@lru_cache(maxsize=4)
def load_retrieval_profile(*, skill_id: str = _SKILL_ID) -> dict[str, Any]:
    return _load_json("retrieval_profile.json", skill_id=skill_id)


def clear_profile_cache() -> None:
    load_disclosure_regimes.cache_clear()
    load_retrieval_profile.cache_clear()


def _normalize_entity_key(s: str) -> str:
    return re.sub(r"\s+", "", (s or "").strip())


def list_entity_aliases(pack: dict[str, Any] | None = None) -> dict[str, str]:
    """alias（归一化）-> canonical entity name。"""
    data = pack or load_disclosure_regimes()
    entities = data.get("entities") or {}
    out: dict[str, str] = {}
    if not isinstance(entities, dict):
        return out
    for canonical, meta in entities.items():
        if not isinstance(meta, dict):
            continue
        keys = [canonical, *list(meta.get("aliases") or [])]
        for k in keys:
            nk = _normalize_entity_key(str(k))
            if nk:
                out[nk] = str(canonical)
    return out


def resolve_regime_for_entity(entity: str, *, pack: dict[str, Any] | None = None) -> str:
    """从问句实体或公司简称解析 disclosure regime id。"""
    data = pack or load_disclosure_regimes()
    entities = data.get("entities") or {}
    regimes = data.get("regimes") or {}
    default = str(data.get("default_regime") or "cn_sz_main")
    fallback = [str(x) for x in (data.get("fallback_regime_order") or []) if str(x).strip()]

    nk = _normalize_entity_key(entity)
    if not nk:
        return default if default in regimes else (fallback[0] if fallback else "cn_sz_main")

    alias_map = list_entity_aliases(data)
    canonical = alias_map.get(nk)
    if canonical and isinstance(entities.get(canonical), dict):
        reg = str((entities[canonical] or {}).get("regime") or "").strip()
        if reg and reg in regimes:
            return reg

    for canonical, meta in entities.items():
        if not isinstance(meta, dict):
            continue
        if nk in _normalize_entity_key(str(canonical)):
            reg = str(meta.get("regime") or "").strip()
            if reg and reg in regimes:
                return reg

    return default if default in regimes else (fallback[0] if fallback else "cn_sz_main")


def regime_config(regime_id: str, *, pack: dict[str, Any] | None = None) -> dict[str, Any]:
    data = pack or load_disclosure_regimes()
    regimes = data.get("regimes") or {}
    if not isinstance(regimes, dict):
        return {}
    cfg = regimes.get(regime_id)
    return dict(cfg) if isinstance(cfg, dict) else {}


def detect_regime_from_text(text: str, *, pack: dict[str, Any] | None = None) -> str | None:
    """从 chunk/问句文本推断 regime（港股英文表头、SEC Item 等），无匹配返回 None。"""
    t = (text or "").replace(" ", "")
    if not t:
        return None
    data = pack or load_disclosure_regimes()
    regimes = data.get("regimes") or {}
    if not isinstance(regimes, dict):
        return None

    sec_markers = ["Item8", "Item7", "10-K", "10-Q", "ConsolidatedBalanceSheets", "MD&A"]
    if any(m.replace(" ", "") in t for m in sec_markers):
        return "sec_us" if "sec_us" in regimes else None

    hk_markers = [
        "综合财务状况表",
        "综合损益表",
        "ManagementDiscussionandAnalysis",
        "ConsolidatedStatementofFinancialPosition",
        "联交所",
        "HKEX",
        "GEM",
    ]
    if any(m.replace(" ", "") in t for m in hk_markers):
        return "hk_main" if "hk_main" in regimes else None

    neeq_markers = ["834195", "430229", "837014", "836333", "全国中小企业股份转让系统"]
    if any(m.replace(" ", "") in t for m in neeq_markers):
        return "cn_neeq" if "cn_neeq" in regimes else None

    return None


def finance_annual_report_skill_enabled(enabled_skill_ids: list[str] | None) -> bool:
    return _SKILL_ID in {str(x).strip() for x in (enabled_skill_ids or []) if str(x).strip()}


def subject_type_from_query(user_query: str) -> str | None:
    """balance_sheet / income_statement / cash_flow；无匹配返回 None。"""
    profile = load_retrieval_profile()
    qj = (user_query or "").replace(" ", "")
    for stype, meta in (profile.get("subject_types") or {}).items():
        if not isinstance(meta, dict):
            continue
        for kw in meta.get("keywords") or []:
            if str(kw) in qj:
                return str(stype)
    return None


def build_finance_retrieval_context(
    enabled_skill_ids: list[str] | None,
    user_query: str,
    *,
    entity: str = "",
) -> dict[str, Any] | None:
    if not finance_annual_report_skill_enabled(enabled_skill_ids):
        return None
    from backend.services.kb_retrieval_plan import detect_entity

    ent = (entity or "").strip() or detect_entity(user_query)
    regime_id = resolve_regime_for_entity(ent)
    subject_type = subject_type_from_query(user_query) or ""
    profile = load_retrieval_profile()
    hints: dict[str, Any] = {}
    if subject_type:
        raw = (profile.get("scoring_hints") or {}).get(subject_type)
        if isinstance(raw, dict):
            hints = raw
    return {
        "active": True,
        "skill_id": _SKILL_ID,
        "regime_id": regime_id,
        "subject_type": subject_type,
        "entity": ent,
        "scoring_hints": hints,
        "regime_config": regime_config(regime_id),
    }


def expand_retrieval_terms_finance(
    terms: list[str],
    query: str,
    finance_context: dict[str, Any],
) -> list[str]:
    """启用财报 skill 时替代通用 compare→利润表 扩展。"""
    out = list(terms or [])
    q = (query or "").strip()
    q_join = q.replace(" ", "")
    regime = finance_context.get("regime_config") if isinstance(finance_context.get("regime_config"), dict) else {}
    aliases = regime.get("query_aliases") if isinstance(regime.get("query_aliases"), dict) else {}
    subject_type = str(finance_context.get("subject_type") or "")

    if re.search(r"(24|25|2024|2025)", q_join):
        out.extend(["2024", "2025", "2024年", "2025年"])
        for tok in regime.get("period_tokens") or []:
            out.append(str(tok))

    if subject_type == "balance_sheet":
        out.extend(list(aliases.get("balance_sheet") or []))
        out.extend(["期末余额", "年末", "合并资产负债表"])
    elif subject_type == "income_statement":
        out.extend(list(aliases.get("income_statement") or []))
        out.extend(["主要会计数据", "主要财务指标"])
        if "营收" in q_join or "收入" in q_join:
            out.append("营业收入")
    elif subject_type == "cash_flow":
        out.extend(list(aliases.get("cash_flow") or []))
    elif "对比" in q_join or "比较" in q_join or "两年" in q_join:
        out.extend(["同比", "两年"])

    regime_id = str(finance_context.get("regime_id") or "")
    profile = load_retrieval_profile()
    templates = profile.get("query_plan_templates") if isinstance(profile.get("query_plan_templates"), dict) else {}
    if regime_id == "hk_main":
        out.extend(templates.get("hk_extra") or [])
    elif regime_id == "sec_us":
        out.extend(templates.get("sec_extra") or [])

    for name in regime.get("statement_names") or []:
        if len(str(name)) >= 2:
            out.append(str(name))

    from backend.services.kb_retrieval_plan import query_wants_change_reasons

    if query_wants_change_reasons(query):
        out.extend(["变动原因", "经营情况讨论", "管理层讨论", "项目重大变动"])

    return list(dict.fromkeys([t for t in out if t and len(str(t)) >= 2]))


def finance_chunk_score_delta(txt: str, query: str, finance_context: dict[str, Any]) -> int:
    delta = 0
    t = txt or ""
    tl = t.lower()
    hints = finance_context.get("scoring_hints") if isinstance(finance_context.get("scoring_hints"), dict) else {}
    for term in hints.get("boost_terms") or []:
        if str(term) in t or str(term).lower() in tl:
            delta += 90
    demote = hints.get("demote_if_only") or []
    if demote and any(str(x) in t for x in demote):
        if not re.search(r"\d{1,3}(?:,\d{3})+\.\d{2}", t):
            delta -= 120
    subject_type = str(finance_context.get("subject_type") or "")
    if subject_type == "balance_sheet" and re.search(r"\d{1,3}(?:,\d{3})+\.\d{2}", t):
        if any(k in t for k in ("合并资产负债表", "资产负债表", "综合财务状况表", "Balance Sheet")):
            delta += 100
    from backend.services.kb_evidence_probe import primary_compare_subject

    primary = primary_compare_subject(query)
    if primary and primary in t and re.search(r"\d{1,3}(?:,\d{3})+\.\d{2}", t):
        if re.search(rf"(?<![\u4e00-\u9fff]){re.escape(primary)}", t):
            delta += 120
    profile = load_retrieval_profile()
    for rule in profile.get("subject_disambiguation") or []:
        if not isinstance(rule, dict):
            continue
        wrong = str(rule.get("wrong") or "").strip()
        not_subj = str(rule.get("not") or "").strip()
        if not wrong or not not_subj or primary != not_subj:
            continue
        if wrong in t and primary not in t:
            delta -= 220
        elif wrong in t and primary in t and not re.search(
            rf"(?<![\u4e00-\u9fff]){re.escape(primary)}[^\n]{{0,40}}\d",
            t,
        ):
            delta -= 80
    from backend.services.kb_retrieval_plan import query_wants_change_reasons

    if query_wants_change_reasons(query):
        for term in (
            "项目重大变动",
            "财务报表项目重大变动",
            "经营情况讨论",
            "管理层讨论",
            "变动原因",
            "主要系",
        ):
            if term in t:
                delta += 75
    return int(delta)


def plan_retrieval_queries_finance(
    user_query: str,
    task_type: Any,
    *,
    entity: str | None = None,
    max_queries: int = 5,
    prefetch_tier: str | None = None,
) -> list[str]:
    from backend.services.kb_retrieval_plan import TaskType, detect_entity, plan_retrieval_queries

    ent = (entity or "").strip() or detect_entity(user_query)
    tt = task_type if isinstance(task_type, TaskType) else TaskType(str(task_type))
    out = plan_retrieval_queries(
        user_query,
        tt,
        entity=ent,
        max_queries=max_queries,
        prefetch_tier=prefetch_tier,
    )
    subject_type = subject_type_from_query(user_query)
    if not subject_type:
        return out
    regime_id = resolve_regime_for_entity(ent)
    profile = load_retrieval_profile()
    templates = profile.get("query_plan_templates") if isinstance(profile.get("query_plan_templates"), dict) else {}
    prefix = f"{ent} " if ent else ""
    extra: list[str] = []

    def _add(s: str) -> None:
        s = (s or "").strip()
        if s and s not in out and s not in extra:
            extra.append(s)

    y1, y2 = "2024", "2025"
    if subject_type == "balance_sheet":
        from backend.services.kb_retrieval_plan import bs_subjects_from_query

        subs = bs_subjects_from_query(user_query) or ["货币资金"]
        subj = subs[0]
        for tpl in templates.get("bs_balance") or []:
            _add(
                tpl.format(entity=ent, subject=subj, y1=y1, y2=y2, subject_en=subj).replace("  ", " ").strip()
            )
    elif subject_type == "income_statement":
        from backend.services.kb_retrieval_plan import fee_subjects_from_query

        subs = fee_subjects_from_query(user_query) or ["营业收入"]
        subj = subs[0]
        for tpl in templates.get("pnl_line") or []:
            _add(tpl.format(entity=ent, subject=subj, y1=y1, y2=y2, subject_en=subj).replace("  ", " ").strip())
        from backend.services.kb_retrieval_plan import query_wants_change_reasons

        if query_wants_change_reasons(user_query):
            for tpl in templates.get("pnl_narrative") or []:
                _add(
                    tpl.format(entity=ent, subject=subj, y1=y1, y2=y2, subject_en=subj)
                    .replace("  ", " ")
                    .strip()
                )
    elif subject_type == "cash_flow":
        from backend.services.kb_retrieval_plan import cf_subjects_from_query

        subs = cf_subjects_from_query(user_query) or ["经营活动产生的现金流量净额"]
        subj = subs[0]
        for tpl in templates.get("cf_line") or []:
            _add(tpl.format(entity=ent, subject=subj, y1=y1, y2=y2, subject_en=subj).replace("  ", " ").strip())

    if regime_id == "hk_main":
        subj = ""
        if subject_type == "balance_sheet":
            from backend.services.kb_retrieval_plan import bs_subjects_from_query

            subs = bs_subjects_from_query(user_query)
            subj = subs[0] if subs else ""
        for tpl in templates.get("hk_extra") or []:
            _add(tpl.format(entity=ent, subject=subj, y1=y1, y2=y2, subject_en=subj).strip())
    elif regime_id == "sec_us":
        subj = ""
        if subject_type == "balance_sheet":
            from backend.services.kb_retrieval_plan import bs_subjects_from_query

            subs = bs_subjects_from_query(user_query)
            subj = subs[0] if subs else ""
        for tpl in templates.get("sec_extra") or []:
            _add(tpl.format(entity=ent, subject=subj, y1=y1, y2=y2, subject_en=subj).strip())

    merged = [out[0]] if out else []
    for q in extra + out[1:]:
        if q not in merged:
            merged.append(q)
    if subject_type == "balance_sheet":
        pl_only = ("利润表", "营业收入", "销售费用", "管理费用", "研发费用", "营业成本", "净利润")
        merged = [
            q
            for q in merged
            if "资产负债表" in q or "合并资产" in q or not any(k in q for k in pl_only)
        ]
    elif subject_type == "cash_flow":
        merged = [q for q in merged if "利润表" not in q or "现金流量" in q]
    return merged[: max(max_queries, len(merged))]


def finance_pack_gaps(
    user_query: str,
    task_type: str,
    *,
    evidence_text: str,
    finance_meta: dict[str, Any] | None,
) -> list[str]:
    if not finance_meta or not finance_meta.get("active"):
        return []
    from backend.services.kb_evidence_probe import blob_has_subject_near_amount, primary_compare_subject
    from backend.services.kb_retrieval_plan import query_wants_change_reasons

    subject_type = str(finance_meta.get("subject_type") or "")
    if task_type != "compare" or not subject_type:
        return []
    profile = load_retrieval_profile()
    required = profile.get("required_evidence") if isinstance(profile.get("required_evidence"), dict) else {}
    subj = primary_compare_subject(user_query)
    if not subj:
        return []
    blob = evidence_text or ""
    gaps: list[str] = []
    if subject_type == "balance_sheet" and not blob_has_subject_near_amount(blob, subj):
        meta = required.get("bs_balance_compare") or {}
        msg = str(meta.get("gap_message") or "").strip()
        if msg:
            gaps.append(msg)
    if subject_type == "income_statement" and not blob_has_subject_near_amount(blob, subj):
        meta = required.get("pnl_amount_compare") or {}
        msg = str(meta.get("gap_message") or "").strip()
        if msg:
            gaps.append(msg)
    if subject_type == "cash_flow" and not blob_has_subject_near_amount(blob, subj):
        meta = required.get("cf_amount_compare") or {}
        msg = str(meta.get("gap_message") or "").strip()
        if msg:
            gaps.append(msg)
    if (
        query_wants_change_reasons(user_query)
        and subject_type == "income_statement"
        and blob_has_subject_near_amount(blob, subj)
        and not _blob_has_narrative_change(blob, subj)
    ):
        meta = required.get("pnl_narrative_change") or {}
        msg = str(meta.get("gap_message") or "").strip()
        if msg:
            gaps.append(msg)
    return gaps


def _blob_has_narrative_change(blob: str, subject: str) -> bool:
    b = blob or ""
    subj = (subject or "").strip()
    if not b:
        return False
    narrative = re.search(
        r"(项目重大变动|财务报表项目重大变动|经营情况讨论|管理层讨论|变动原因|主要系|同比下降|同比上升|驱动)",
        b,
    )
    if not narrative:
        return False
    if subj and subj in b:
        return True
    return bool(narrative)


def supplemental_prefers_gap_driven(enabled_skill_ids: list[str] | None) -> bool:
    if not finance_annual_report_skill_enabled(enabled_skill_ids):
        return False
    profile = load_retrieval_profile()
    pol = profile.get("supplemental_policy") if isinstance(profile.get("supplemental_policy"), dict) else {}
    return bool(pol.get("prefer_gaps_over_narrative_filter"))
