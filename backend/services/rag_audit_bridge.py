"""
1.2.0.d：RAG / 回答审计统一入口（knowledge.ask + ai-interaction.chat）。
"""

from __future__ import annotations

from typing import Any

from backend.config import settings
from backend.services.knowledge_audit import write_event
from backend.services.online_rate_limiter import allow as rate_limit_allow
from backend.services.task_queue import get_stats as get_queue_stats

# re-export for tests
__all__ = [
    "audit_retrieve_attempt",
    "audit_retrieve_deny",
    "audit_answer_generate",
    "audit_answer_deny",
    "audit_after_ask_result",
    "run_pre_ask_guards",
    "write_event",
]


def _safe_write(
    tenant_id: str,
    *,
    username: str | None,
    event_type: str,
    query: str | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    try:
        write_event(tenant_id, username=username, event_type=event_type, query=query, meta=meta)
    except Exception:
        pass


def audit_retrieve_attempt(
    tenant_id: str,
    *,
    username: str | None,
    query: str | None,
    meta: dict[str, Any] | None = None,
) -> None:
    _safe_write(
        tenant_id,
        username=username,
        event_type="knowledge.retrieve.attempt",
        query=query,
        meta=meta,
    )


def audit_retrieve_deny(
    tenant_id: str,
    *,
    username: str | None,
    query: str | None,
    reason: str,
    meta: dict[str, Any] | None = None,
) -> None:
    m = dict(meta or {})
    m["reason"] = reason
    _safe_write(
        tenant_id,
        username=username,
        event_type="knowledge.retrieve.deny",
        query=query,
        meta=m,
    )


def audit_answer_generate(
    tenant_id: str,
    *,
    username: str | None,
    query: str | None,
    citations: list[dict[str, Any]] | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    cites = list(citations or [])
    m = dict(meta or {})
    m.setdefault("citation_count", len(cites))
    m.setdefault(
        "doc_ids",
        sorted({str(c.get("doc_id")) for c in cites if c.get("doc_id")}),
    )
    m.setdefault(
        "table_ids",
        sorted({str(c.get("table_id")) for c in cites if c.get("table_id")}),
    )
    _safe_write(
        tenant_id,
        username=username,
        event_type="ai.answer.generate",
        query=query,
        meta=m,
    )


def audit_answer_deny(
    tenant_id: str,
    *,
    username: str | None,
    query: str | None,
    reason: str,
    meta: dict[str, Any] | None = None,
) -> None:
    m = dict(meta or {})
    m["reason"] = reason
    _safe_write(
        tenant_id,
        username=username,
        event_type="ai.answer.deny",
        query=query,
        meta=m,
    )


def audit_after_ask_result(
    tenant_id: str,
    *,
    username: str | None,
    query: str | None,
    result: dict[str, Any],
    extra_meta: dict[str, Any] | None = None,
) -> None:
    if result.get("denied"):
        audit_retrieve_deny(
            tenant_id,
            username=username,
            query=query,
            reason=str(result.get("deny_reason") or "denied"),
            meta=extra_meta,
        )
        return
    audit_answer_generate(
        tenant_id,
        username=username,
        query=query,
        citations=list(result.get("citations") or []),
        meta=extra_meta,
    )


def run_pre_ask_guards(
    tenant_id: str,
    *,
    username: str | None,
    query: str | None,
    rate_limit_key: str,
    channel: str,
) -> str | None:
    """
    返回 deny reason 字符串；None 表示通过。
    队列堆积 / 限速时写 ai.answer.deny。
    """
    base_meta = {"channel": channel}
    try:
        qs = get_queue_stats()
        if int(qs.get("queue_size_high") or 0) >= int(settings.queue_degrade_high_threshold):
            audit_answer_deny(
                tenant_id,
                username=username,
                query=query,
                reason="queue_backpressure",
                meta={**base_meta, "queue_size_high": qs.get("queue_size_high")},
            )
            return "queue_backpressure"
    except Exception:
        pass

    if not rate_limit_allow(key=rate_limit_key):
        audit_answer_deny(
            tenant_id,
            username=username,
            query=query,
            reason="rate_limited",
            meta=base_meta,
        )
        return "rate_limited"
    return None
