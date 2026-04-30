import uuid

import jwt
from fastapi.testclient import TestClient

from backend.config import settings
from backend.main import app
from backend.services.kb_collections import dynamic_private_collection_id


def _token(username: str) -> str:
    return jwt.encode({"sub": username}, settings.auth_secret, algorithm="HS256")


def test_kb_share_add_scope_keeps_private_and_sets_kind():
    client = TestClient(app)
    username = "pytest_user_share_add"
    auth = {"Authorization": f"Bearer {_token(username)}"}
    name = f"pytest_share_add_{uuid.uuid4().hex[:8]}"

    r = client.post("/api/knowledge/folders", headers=auth, json={"name": name})
    assert r.status_code == 200, r.text
    fid = (r.json() or {}).get("folder_id")
    assert isinstance(fid, str) and fid

    rr0 = client.get(f"/api/knowledge/folders/{fid}/resources", headers=auth)
    assert rr0.status_code == 200, rr0.text
    f0 = (rr0.json() or {}).get("folder") or {}
    assert str(f0.get("kind") or "") == "Private"

    r2 = client.post(
        f"/api/knowledge/folders/{fid}/share-add-scope",
        headers=auth,
        json={"target": "company", "access_kind": "public", "department_ids": [], "project_ids": []},
    )
    assert r2.status_code == 200, r2.text
    assert (r2.json() or {}).get("ok") is True

    rr1 = client.get(f"/api/knowledge/folders/{fid}/resources", headers=auth)
    assert rr1.status_code == 200, rr1.text
    f1 = (rr1.json() or {}).get("folder") or {}
    assert str(f1.get("kind") or "") == "CompanyPublic"
    cids = list(f1.get("collection_ids") or [])
    assert dynamic_private_collection_id(username) in cids

    # revoke all shares -> back to private only
    r3 = client.post(f"/api/knowledge/folders/{fid}/unshare", headers=auth)
    assert r3.status_code == 200, r3.text
    rr2 = client.get(f"/api/knowledge/folders/{fid}/resources", headers=auth)
    assert rr2.status_code == 200, rr2.text
    f2 = (rr2.json() or {}).get("folder") or {}
    assert str(f2.get("kind") or "") == "Private"
    cids2 = list(f2.get("collection_ids") or [])
    assert cids2 == [dynamic_private_collection_id(username)]

    r4 = client.delete(f"/api/knowledge/folders/{fid}", headers=auth)
    assert r4.status_code == 200, r4.text

