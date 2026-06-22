"""知识库文件夹增量上传：子树 source_hash 跳过重复。"""

from __future__ import annotations

import io
import uuid

import jwt
from fastapi.testclient import TestClient

from backend.config import settings
from backend.main import app
from backend.services.dev_users import ensure_department_test_user
from backend.services.kb_documents import compute_source_hash
from backend.services.knowledge_acl import load_fixtures

client = TestClient(app)

USER = "kb_incr_upload_pytest"
PWD = "KbIncrUpload!2026"


def _auth(username: str) -> dict[str, str]:
    token = jwt.encode({"sub": username}, settings.auth_secret, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def _ensure_user() -> None:
    ensure_department_test_user(USER, password=PWD, department="财务部", roles=[])


def test_incremental_upload_skips_duplicate_hash_in_folder_subtree():
    _ensure_user()
    auth = _auth(USER)
    fixtures = load_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"

    name = f"pytest_incr_{uuid.uuid4().hex[:8]}"
    r_folder = client.post("/api/knowledge/folders", headers=auth, json={"name": name})
    assert r_folder.status_code == 200, r_folder.text
    fid = r_folder.json()["folder_id"]

    content = b"incremental upload pytest unique payload 42"
    h = compute_source_hash(content)

    r1 = client.post(
        "/api/knowledge/my-documents/upload",
        headers=auth,
        data={"folder_id": fid, "source_hash": h},
        files={"file": ("first.txt", io.BytesIO(content), "text/plain")},
    )
    assert r1.status_code == 200, r1.text
    body1 = r1.json()
    assert body1.get("skipped") is False, body1
    doc_id = body1["doc_id"]

    r_preflight = client.post(
        f"/api/knowledge/folders/{fid}/existing-source-hashes",
        headers=auth,
        json={"source_hashes": [h]},
    )
    assert r_preflight.status_code == 200, r_preflight.text
    assert r_preflight.json().get("items", {}).get(h) == doc_id

    r2 = client.post(
        "/api/knowledge/my-documents/upload",
        headers=auth,
        data={"folder_id": fid, "source_hash": h},
        files={"file": ("second_copy.txt", io.BytesIO(content), "text/plain")},
    )
    assert r2.status_code == 200, r2.text
    body2 = r2.json()
    assert body2.get("skipped") is True, body2
    assert body2.get("doc_id") == doc_id
    assert body2.get("skip_reason") == "duplicate_hash"

    rr = client.get(f"/api/knowledge/folders/{fid}/resources", headers=auth)
    assert rr.status_code == 200, rr.text
    doc_ids = [d["doc_id"] for d in (rr.json().get("docs") or []) if d.get("doc_id")]
    assert doc_ids.count(doc_id) == 1, doc_ids

    client.delete(f"/api/knowledge/my-documents/{doc_id}", headers=auth)
    client.delete(f"/api/knowledge/folders/{fid}", headers=auth)


def test_same_hash_outside_folder_subtree_still_uploads():
    _ensure_user()
    auth = _auth(USER)
    name_a = f"pytest_incr_a_{uuid.uuid4().hex[:8]}"
    name_b = f"pytest_incr_b_{uuid.uuid4().hex[:8]}"
    r_a = client.post("/api/knowledge/folders", headers=auth, json={"name": name_a})
    r_b = client.post("/api/knowledge/folders", headers=auth, json={"name": name_b})
    assert r_a.status_code == 200 and r_b.status_code == 200
    fid_a = r_a.json()["folder_id"]
    fid_b = r_b.json()["folder_id"]

    content = b"cross folder hash test 99"
    h = compute_source_hash(content)
    r1 = client.post(
        "/api/knowledge/my-documents/upload",
        headers=auth,
        data={"folder_id": fid_a, "source_hash": h},
        files={"file": ("a.txt", io.BytesIO(content), "text/plain")},
    )
    assert r1.status_code == 200, r1.text
    doc_a = r1.json()["doc_id"]

    r2 = client.post(
        "/api/knowledge/my-documents/upload",
        headers=auth,
        data={"folder_id": fid_b, "source_hash": h},
        files={"file": ("b.txt", io.BytesIO(content), "text/plain")},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json().get("skipped") is False, r2.json()
    doc_b = r2.json()["doc_id"]
    assert doc_b != doc_a

    client.delete(f"/api/knowledge/my-documents/{doc_a}", headers=auth)
    client.delete(f"/api/knowledge/my-documents/{doc_b}", headers=auth)
    client.delete(f"/api/knowledge/folders/{fid_a}", headers=auth)
    client.delete(f"/api/knowledge/folders/{fid_b}", headers=auth)
