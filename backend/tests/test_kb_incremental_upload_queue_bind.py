"""增量上传：队列满时仍绑定文件夹，重传可跳过。"""

from __future__ import annotations

import io
import uuid
from unittest.mock import patch

import jwt
from fastapi.testclient import TestClient

from backend.config import settings
from backend.main import app
from backend.services.dev_users import ensure_department_test_user
from backend.services.kb_documents import compute_source_hash

client = TestClient(app)

USER = "kb_incr_queue_pytest"
PWD = "KbIncrQueue!2026"


def _auth(username: str) -> dict[str, str]:
    token = jwt.encode({"sub": username}, settings.auth_secret, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def test_queue_full_still_binds_folder_then_retry_skips():
    ensure_department_test_user(USER, password=PWD, department="财务部", roles=[])
    auth = _auth(USER)
    name = f"pytest_queue_{uuid.uuid4().hex[:8]}"
    r_folder = client.post("/api/knowledge/folders", headers=auth, json={"name": name})
    assert r_folder.status_code == 200, r_folder.text
    fid = r_folder.json()["folder_id"]

    content = b"queue full bind folder retry skip"
    h = compute_source_hash(content)

    with patch("backend.routers.knowledge._enqueue_user_doc_with_retry", return_value=False):
        r1 = client.post(
            "/api/knowledge/my-documents/upload",
            headers=auth,
            data={"folder_id": fid, "source_hash": h},
            files={"file": ("q.txt", io.BytesIO(content), "text/plain")},
        )
    assert r1.status_code == 503, r1.text

    rr = client.get(f"/api/knowledge/folders/{fid}/resources", headers=auth)
    assert rr.status_code == 200, rr.text
    doc_ids = [d["doc_id"] for d in (rr.json().get("docs") or []) if d.get("doc_id")]
    assert len(doc_ids) == 1, "队列满时文档仍应出现在目标文件夹"

    with patch("backend.routers.knowledge._enqueue_user_doc_with_retry", return_value=True):
        r2 = client.post(
            "/api/knowledge/my-documents/upload",
            headers=auth,
            data={"folder_id": fid, "source_hash": h},
            files={"file": ("q2.txt", io.BytesIO(content), "text/plain")},
        )
    assert r2.status_code == 200, r2.text
    assert r2.json().get("skipped") is True, r2.json()
    assert r2.json().get("doc_id") == doc_ids[0]

    client.delete(f"/api/knowledge/my-documents/{doc_ids[0]}", headers=auth)
    client.delete(f"/api/knowledge/folders/{fid}", headers=auth)
