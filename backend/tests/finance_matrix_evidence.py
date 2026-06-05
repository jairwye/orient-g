"""财务矩阵测试：复用 services 层通用证据探测（勿在此写 probe 硬编码）。"""

from __future__ import annotations



from typing import Any



from backend.services.kb_evidence_probe import (

    build_evidence_probe_query,

    blob_has_subject_near_amount,

    primary_compare_subject,

    probe_kb_evidence_for_query,

    reply_matches_kb_evidence,

    reply_says_honest_missing,

)

from backend.services.knowledge_acl import load_fixtures

from backend.services.kb_scope_resolve import resolve_kb_scope_for_ask

from backend.tests.test_acl_folder_shared_docs import FOLDER_JINGPIN_CAIBAO_25





def probe_subject_kb(token: str, subject: str, *, user_query: str = "") -> dict[str, Any]:

    """兼容旧接口：优先用 user_query 问句驱动探测，subject 仅作 fallback 标签。"""

    scope = {"selected_folder_ids": [FOLDER_JINGPIN_CAIBAO_25]}

    fixtures = load_fixtures()

    resolved = resolve_kb_scope_for_ask("tenant1", scope)

    q = user_query.strip() if user_query else ""

    if not q and subject:

        q = f"{subject} 2024 2025 对比"

    return probe_kb_evidence_for_query(

        token,

        q,

        scope,

        fixtures=fixtures,

        resolved_scope=resolved,

        subject=subject,

    )





def reply_matches_kb(reply: str, *, subject: str, kb_probe: dict[str, Any]) -> bool:

    user_query = str(kb_probe.get("user_query") or "")

    if not user_query and subject:

        user_query = f"{subject} 对比"

    return reply_matches_kb_evidence(

        reply,

        user_query=user_query,

        kb_probe=kb_probe,

        subject=subject,

    )





__all__ = [

    "build_evidence_probe_query",

    "blob_has_subject_near_amount",

    "primary_compare_subject",

    "probe_kb_evidence_for_query",

    "probe_subject_kb",

    "reply_matches_kb",

    "reply_matches_kb_evidence",

    "reply_says_honest_missing",

]

