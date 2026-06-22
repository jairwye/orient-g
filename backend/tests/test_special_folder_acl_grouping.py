"""特殊知识库管理后台：按文件夹归集，避免逐文档膨胀。"""

from __future__ import annotations

import jwt
from fastapi.testclient import TestClient

from backend.config import settings
from backend.main import app
from backend.tests.test_acl_folder_shared_docs import FOLDER_JINGPIN_CAIBAO_25

client = TestClient(app)


def test_special_docs_grouped_by_folder_not_per_doc():
    token = jwt.encode({"sub": "admin"}, settings.auth_secret, algorithm="HS256")
    r = client.get("/api/settings/kb-meta/special-docs", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    items = r.json().get("items") or []
    assert len(items) < 50, f"expected folder rows, got {len(items)} items"
    jingpin = next((x for x in items if x.get("folder_id") == FOLDER_JINGPIN_CAIBAO_25), None)
    assert jingpin is not None, [x.get("name") for x in items[:10]]
    assert jingpin.get("doc_count", 0) > 50
    assert "doc_id" not in jingpin
    assert (jingpin.get("acl") or {}).get("allow_management") is True


def test_unfiled_bucket_excludes_private_docs_without_special_share():
    """私人未归档文档不应进入「单独共享」桶，更不应显示全员可读。"""
    from backend.services.dev_users import ensure_department_test_user
    from backend.services.kb_acl_store import merge_resource_assignments

    owner = "unfiled_bucket_owner_py"
    ensure_department_test_user(owner, password="UnfiledBucket!2026", department="研发部", roles=[])
    token = jwt.encode({"sub": "admin"}, settings.auth_secret, algorithm="HS256")
    auth = {"Authorization": f"Bearer {token}"}
    client_auth = jwt.encode({"sub": owner}, settings.auth_secret, algorithm="HS256")
    owner_auth = {"Authorization": f"Bearer {client_auth}"}

    r_up = client.post(
        "/api/knowledge/my-documents/upload",
        headers=owner_auth,
        files={"file": ("private_only.txt", b"private unfiled only", "text/plain")},
    )
    assert r_up.status_code == 200, r_up.text
    doc_id = r_up.json()["doc_id"]

    # 模拟错误数据：仅 assignment 误绑公司公共库，但无 share 记录（不应算「单独共享」）
    merge_resource_assignments(
        "tenant1",
        resource_type="doc",
        resource_id=doc_id,
        collection_ids=["c_company_public_1"],
    )

    r = client.get("/api/settings/kb-meta/special-docs", headers=auth)
    assert r.status_code == 200, r.text
    items = r.json().get("items") or []
    unfiled = next((x for x in items if x.get("folder_id") == "__unfiled__"), None)
    if unfiled:
        assert doc_id not in (unfiled.get("doc_ids") or []), unfiled
        assert not (unfiled.get("acl") or {}).get("allow_all"), unfiled

    client.delete(f"/api/knowledge/my-documents/{doc_id}", headers=owner_auth)
