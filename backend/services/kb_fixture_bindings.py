"""将 fixtures 中的财务华清验收文档/表绑定到 c_finance_public_1（幂等）。"""

from __future__ import annotations

from backend.services.kb_acl_store import set_resource_assignments

HUAQING_DOC_ID = "d_finance_huaqing_pl_1"
HUAQING_TABLE_ID = "t_huaqing_pl_compare_1"
FINANCE_PUBLIC_COLLECTION = "c_finance_public_1"


def ensure_finance_huaqing_fixture_bindings(tenant_id: str = "tenant1") -> None:
    set_resource_assignments(
        tenant_id,
        resource_type="doc",
        resource_id=HUAQING_DOC_ID,
        collection_ids=[FINANCE_PUBLIC_COLLECTION],
    )
    set_resource_assignments(
        tenant_id,
        resource_type="table",
        resource_id=HUAQING_TABLE_ID,
        collection_ids=[FINANCE_PUBLIC_COLLECTION],
    )
