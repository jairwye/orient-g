"""管理层知识库 ACL：取消全库 bypass，文件夹分享到管理层后可读。"""

from __future__ import annotations

import io
import uuid

import jwt
from fastapi.testclient import TestClient

from backend.config import settings
from backend.main import app
from backend.services.dev_users import ensure_department_test_user
from backend.services.knowledge_acl import compute_acl_scope, load_fixtures
from backend.services.user_acl_store import ROLE_MANAGEMENT

client = TestClient(app)

OWNER = "mgmt_acl_owner_pytest"
MGMT = "mgmt_acl_mgmt_pytest"
OWNER_PWD = "MgmtAclOwner!2026"
MGMT_PWD = "MgmtAclMgmt!2026"


def _token(username: str) -> str:
    return jwt.encode({"sub": username}, settings.auth_secret, algorithm="HS256")


def _auth(username: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(username)}"}


def _ensure_users() -> None:
    ensure_department_test_user(OWNER, password=OWNER_PWD, department="研发部", roles=[])
    ensure_department_test_user(
        MGMT,
        password=MGMT_PWD,
        department="总裁办",
        roles=[ROLE_MANAGEMENT],
    )


def _login_token(username: str, password: str) -> str:
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def test_management_no_full_bypass_and_share_grants_read():
    _ensure_users()
    fixtures = load_fixtures()
    owner_auth = _auth(OWNER)
    mgmt_token = _login_token(MGMT, MGMT_PWD)
    admin_token = _login_token("admin", "123456")

    name = f"pytest_mgmt_share_{uuid.uuid4().hex[:8]}"
    r_folder = client.post("/api/knowledge/folders", headers=owner_auth, json={"name": name})
    assert r_folder.status_code == 200, r_folder.text
    fid = r_folder.json()["folder_id"]

    content = b"mgmt acl pytest secret content 98765"
    r_up = client.post(
        "/api/knowledge/my-documents/upload",
        headers=owner_auth,
        data={"folder_id": fid},
        files={"file": ("mgmt_test.txt", io.BytesIO(content), "text/plain")},
    )
    assert r_up.status_code == 200, r_up.text
    doc_id = r_up.json()["doc_id"]

    scope_mgmt_before = compute_acl_scope(mgmt_token, fixtures=fixtures)
    assert doc_id not in set(scope_mgmt_before.get("allowed_doc_ids") or [])

    scope_admin = compute_acl_scope(admin_token, fixtures=fixtures)
    admin_docs = set(scope_admin.get("allowed_doc_ids") or [])
    mgmt_docs_before = set(scope_mgmt_before.get("allowed_doc_ids") or [])
    assert len(admin_docs) > len(mgmt_docs_before) + 10, "admin 应保留全库 bypass，管理层不应"

    r_share = client.post(
        f"/api/knowledge/folders/{fid}/share-add-scope",
        headers=owner_auth,
        json={"target": "management", "access_kind": "public", "department_ids": [], "project_ids": []},
    )
    assert r_share.status_code == 200, r_share.text
    assert "c_management_public_1" in (r_share.json().get("collection_ids") or [])

    scope_mgmt_after = compute_acl_scope(mgmt_token, fixtures=fixtures)
    assert doc_id in set(scope_mgmt_after.get("allowed_doc_ids") or [])

    mgmt_auth = {"Authorization": f"Bearer {mgmt_token}"}
    r_resources = client.get(f"/api/knowledge/folders/{fid}/resources", headers=mgmt_auth)
    assert r_resources.status_code == 200, r_resources.text
    res_doc_ids = [
        d.get("doc_id")
        for d in (r_resources.json().get("docs") or [])
        if d and d.get("doc_id")
    ]
    assert doc_id in res_doc_ids, "管理层用户应能打开已分享文件夹并读取文档"

    admin_auth = {"Authorization": f"Bearer {admin_token}"}
    r_special = client.get("/api/settings/kb-meta/special-docs", headers=admin_auth)
    assert r_special.status_code == 200, r_special.text
    items = r_special.json().get("items") or []
    hit = next((x for x in items if x.get("folder_id") == fid), None)
    assert hit is not None, "分享后应出现在特殊知识库文件夹列表"
    assert hit.get("doc_count", 0) >= 1
    acl = hit.get("acl") or {}
    assert acl.get("allow_management") is True, hit

    client.post(f"/api/knowledge/folders/{fid}/unshare", headers=owner_auth)
    client.delete(f"/api/knowledge/folders/{fid}", headers=owner_auth)
