import uuid

import jwt
from fastapi.testclient import TestClient

from backend.config import settings
from backend.main import app


def _token(username: str) -> str:
    return jwt.encode({"sub": username}, settings.auth_secret, algorithm="HS256")


def test_kb_move_folder_to_kb_private_then_company_then_private():
    client = TestClient(app)
    auth = {"Authorization": f"Bearer {_token('pytest_user_move')}"}
    name = f"pytest_move_kb_{uuid.uuid4().hex[:8]}"
    r = client.post("/api/knowledge/folders", headers=auth, json={"name": name})
    assert r.status_code == 200, r.text
    fid = (r.json() or {}).get("folder_id")
    assert isinstance(fid, str) and fid

    def folder_kind() -> str:
        rr = client.get(f"/api/knowledge/folders/{fid}/resources", headers=auth)
        assert rr.status_code == 200, rr.text
        payload = rr.json() or {}
        folder = payload.get("folder") or {}
        return str(folder.get("kind") or "")

    assert folder_kind() == "Private"

    r2 = client.post(
        f"/api/knowledge/folders/{fid}/move-to-kb",
        headers=auth,
        json={
            "kb_kind": "CompanyPublic",
            "department_ids": [],
            "project_ids": [],
            "company_public": True,
        },
    )
    assert r2.status_code == 200, r2.text
    assert (r2.json() or {}).get("ok") is True
    assert folder_kind() == "CompanyPublic"

    r3 = client.post(
        f"/api/knowledge/folders/{fid}/move-to-kb",
        headers=auth,
        json={"kb_kind": "Private", "department_ids": [], "project_ids": [], "company_public": False},
    )
    assert r3.status_code == 200, r3.text
    assert folder_kind() == "Private"

    r4 = client.delete(f"/api/knowledge/folders/{fid}", headers=auth)
    assert r4.status_code == 200, r4.text
