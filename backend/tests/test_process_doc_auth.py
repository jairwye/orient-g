import jwt
from fastapi.testclient import TestClient

from backend.config import settings
from backend.main import app


def _headers(username: str) -> dict[str, str]:
    token = jwt.encode({"sub": username}, settings.auth_secret, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def test_process_doc_schema_requires_auth():
    client = TestClient(app)
    res = client.get("/api/process-doc/schema")
    assert res.status_code == 401, res.text


def test_process_doc_schema_forbidden_for_non_admin(monkeypatch):
    from backend.routers import process_doc as mod

    monkeypatch.setattr(mod, "get_user", lambda _u: {"roles": []})
    client = TestClient(app)
    res = client.get("/api/process-doc/schema", headers=_headers("alice"))
    assert res.status_code == 403, res.text

