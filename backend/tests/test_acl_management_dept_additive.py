"""部门分享后再叠加管理层：kind 保持 DeptPublic，子树文档进入特殊知识库列表。"""

from __future__ import annotations

import io
import uuid

import jwt
from fastapi.testclient import TestClient

from backend.config import settings
from backend.main import app
from backend.routers.settings import DEPARTMENT_FINANCE
from backend.services.dev_users import ensure_department_test_user
from backend.services.kb_documents import list_docs_touching_collections, SPECIAL_ADMIN_COLLECTION_IDS
from backend.services.knowledge_acl import load_fixtures

client = TestClient(app)

OWNER = "mgmt_dept_owner_pytest"
FINANCE = "mgmt_dept_fin_pytest"
OWNER_PWD = "MgmtDeptOwner!2026"
FIN_PWD = "MgmtDeptFin!2026"


def _auth(username: str) -> dict[str, str]:
    token = jwt.encode({"sub": username}, settings.auth_secret, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def _ensure_users() -> None:
    ensure_department_test_user(OWNER, password=OWNER_PWD, department="研发部", roles=[])
    ensure_department_test_user(
        FINANCE,
        password=FIN_PWD,
        department=DEPARTMENT_FINANCE,
        roles=[],
        is_department_lead=False,
    )


def test_dept_share_then_management_keeps_dept_kind_and_special_docs():
    _ensure_users()
    fixtures = load_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    owner_auth = _auth(OWNER)

    name = f"pytest_dept_mgmt_{uuid.uuid4().hex[:8]}"
    r_folder = client.post("/api/knowledge/folders", headers=owner_auth, json={"name": name})
    assert r_folder.status_code == 200, r_folder.text
    fid = r_folder.json()["folder_id"]

    r_up = client.post(
        "/api/knowledge/my-documents/upload",
        headers=owner_auth,
        data={"folder_id": fid},
        files={"file": ("additive.txt", io.BytesIO(b"dept then mgmt"), "text/plain")},
    )
    assert r_up.status_code == 200, r_up.text
    doc_id = r_up.json()["doc_id"]

    r_dept = client.post(
        f"/api/knowledge/folders/{fid}/share-add-scope",
        headers=owner_auth,
        json={
            "target": "department",
            "access_kind": "public",
            "department_ids": [DEPARTMENT_FINANCE],
            "project_ids": [],
        },
    )
    assert r_dept.status_code == 200, r_dept.text

    r_mgmt = client.post(
        f"/api/knowledge/folders/{fid}/share-add-scope",
        headers=owner_auth,
        json={"target": "management", "access_kind": "public", "department_ids": [], "project_ids": []},
    )
    assert r_mgmt.status_code == 200, r_mgmt.text

    rr = client.get("/api/knowledge/folders", headers=owner_auth)
    assert rr.status_code == 200, rr.text
    folder_item = next((x for x in (rr.json().get("items") or []) if x.get("folder_id") == fid), None)
    assert folder_item is not None
    assert str(folder_item.get("kind") or "") == "DeptPublic", folder_item
    share_kinds = folder_item.get("share_kinds") or []
    assert "DeptPublic" in share_kinds, share_kinds
    assert "ManagementPublic" in share_kinds, share_kinds

    fin_auth = _auth(FINANCE)
    r_list = client.get("/api/knowledge/folders", headers=fin_auth)
    assert r_list.status_code == 200, r_list.text
    names = [x.get("name") for x in (r_list.json().get("items") or []) if x.get("folder_id") == fid]
    assert names == [name], "财务部用户应在部门公共库仍可见该文件夹"

    touching = list_docs_touching_collections(tenant_id, set(SPECIAL_ADMIN_COLLECTION_IDS))
    hit = next((x for x in touching if x.get("doc_id") == doc_id), None)
    assert hit is not None, "子树文档应绑定管理层 collection 并出现在特殊文档候选"
    assert "c_management_public_1" in (hit.get("collection_ids") or []), hit

    admin_auth = _auth("admin")
    r_special = client.get("/api/settings/kb-meta/special-docs", headers=admin_auth)
    assert r_special.status_code == 200, r_special.text
    items = r_special.json().get("items") or []
    spec = next((x for x in items if x.get("folder_id") == fid), None)
    assert spec is not None, items[:3]
    assert spec.get("doc_count", 0) >= 1
    assert (spec.get("acl") or {}).get("allow_management") is True

    client.post(f"/api/knowledge/folders/{fid}/unshare", headers=owner_auth)
    client.delete(f"/api/knowledge/folders/{fid}", headers=owner_auth)
