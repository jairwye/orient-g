import uuid

import jwt
from fastapi.testclient import TestClient

from backend.config import settings
from backend.main import app


def _token(username: str) -> str:
    return jwt.encode({"sub": username}, settings.auth_secret, algorithm="HS256")


def test_kb_create_folder_ok():
    client = TestClient(app)
    name = f"pytest_folder_{uuid.uuid4().hex[:8]}"
    r = client.post(
        "/api/knowledge/folders",
        headers={"Authorization": f"Bearer {_token('pytest_user')}"},
        json={"name": name},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("ok") is True
    assert isinstance(data.get("folder_id"), str) and data["folder_id"]

    # delete should succeed for normal folder
    fid = data["folder_id"]
    r2 = client.delete(
        f"/api/knowledge/folders/{fid}",
        headers={"Authorization": f"Bearer {_token('pytest_user')}"},
    )
    assert r2.status_code == 200, r2.text
    assert (r2.json() or {}).get("ok") is True

