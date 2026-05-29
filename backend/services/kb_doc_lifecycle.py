"""
1.2.0.c：通用用户文档状态机（upload → parse → package → active）。

bigpdf 任务另有独立 stage；本模块仅约束 kb_user_documents.status。
"""

from __future__ import annotations

from typing import Final

from sqlalchemy import text

from backend.database import get_db

DOC_STATUSES: Final[frozenset[str]] = frozenset(
    {
        "uploaded",
        "queued",
        "parsing",
        "parsed",
        "packaged",
        "assigned",
        "active",
        "failed",
    }
)

# assigned：内网闭环下打包后即视为已归属（与 kb_documents 注释一致）
ALLOWED_TRANSITIONS: Final[dict[str, frozenset[str]]] = {
    "uploaded": frozenset({"parsing", "parsed", "failed"}),
    "queued": frozenset({"parsing", "failed"}),
    "parsing": frozenset({"parsed", "failed"}),
    "parsed": frozenset({"packaged", "failed"}),
    "packaged": frozenset({"assigned", "active", "failed"}),
    "assigned": frozenset({"active", "failed"}),
    "active": frozenset({"failed"}),
    "failed": frozenset({"queued", "uploaded"}),
}


class InvalidDocStatusTransition(ValueError):
    pass


def can_transition(from_status: str | None, to_status: str, *, raise_on_invalid: bool = False) -> bool:
    src = (from_status or "").strip() or "uploaded"
    dst = (to_status or "").strip()
    if dst not in DOC_STATUSES:
        if raise_on_invalid:
            raise InvalidDocStatusTransition(f"unknown status: {dst}")
        return False
    allowed = ALLOWED_TRANSITIONS.get(src, frozenset())
    ok = dst in allowed or src == dst
    if not ok and raise_on_invalid:
        raise InvalidDocStatusTransition(f"{src} -> {dst} not allowed")
    return ok


def _update_status_row(
    tenant_id: str,
    doc_id: str,
    status: str,
    *,
    last_error: str | None = None,
    manifest_json: str | None = None,
    parser_version: str | None = None,
    source_hash: str | None = None,
) -> None:
    sets = ["status=:st", "updated_at=CURRENT_TIMESTAMP"]
    params: dict = {"t": tenant_id, "d": doc_id, "st": status}
    if last_error is not None:
        sets.append("last_error=:err")
        params["err"] = (last_error or "")[:4000]
    else:
        sets.append("last_error=NULL")
    if manifest_json is not None:
        sets.append("manifest_json=:mj")
        params["mj"] = manifest_json
    if parser_version is not None:
        sets.append("parser_version=:pv")
        params["pv"] = parser_version
    if source_hash is not None:
        sets.append("source_hash=:h")
        params["h"] = source_hash
    sql = f"UPDATE kb_user_documents SET {', '.join(sets)} WHERE tenant_id=:t AND doc_id=:d"
    with get_db() as db:
        db.execute(text(sql), params)


def transition_document_status(
    tenant_id: str,
    doc_id: str,
    to_status: str,
    *,
    from_status: str | None = None,
    last_error: str | None = None,
    manifest_json: str | None = None,
    parser_version: str | None = None,
    source_hash: str | None = None,
    skip_validation: bool = False,
) -> None:
    if not skip_validation:
        can_transition(from_status, to_status, raise_on_invalid=True)
    _update_status_row(
        tenant_id,
        doc_id,
        to_status,
        last_error=last_error,
        manifest_json=manifest_json,
        parser_version=parser_version,
        source_hash=source_hash,
    )


def manifest_required_keys() -> frozenset[str]:
    return frozenset(
        {
            "doc_id",
            "doc_version",
            "tenant_id",
            "section_count",
            "sections",
            "source_hash",
            "parser_version",
        }
    )


def validate_manifest(manifest: dict) -> list[str]:
    missing = [k for k in manifest_required_keys() if k not in manifest]
    return missing
