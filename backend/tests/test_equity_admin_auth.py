import jwt
from fastapi.testclient import TestClient

from backend.config import settings
from backend.main import app


def _headers(username: str) -> dict[str, str]:
    token = jwt.encode({"sub": username}, settings.auth_secret, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def test_equity_admin_import_requires_auth():
    client = TestClient(app)
    res = client.post(
        "/api/equity/admin/import",
        json={"snapshot_name": "s1", "entities": [], "edges": [], "targets": []},
    )
    assert res.status_code == 401, res.text


def test_equity_admin_import_forbidden_for_non_admin(monkeypatch):
    from backend.routers import equity as mod

    monkeypatch.setattr(mod, "get_user", lambda _u: {"roles": []})
    client = TestClient(app)
    res = client.post(
        "/api/equity/admin/import",
        headers=_headers("alice"),
        json={"snapshot_name": "s1", "entities": [], "edges": [], "targets": []},
    )
    assert res.status_code == 403, res.text

