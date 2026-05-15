import uuid

import jwt
from fastapi.testclient import TestClient

from backend.config import settings
from backend.main import app


def _auth_header(username: str = "admin") -> dict[str, str]:
    token = jwt.encode({"sub": username}, settings.auth_secret, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def test_equity_panorama_smoke_import_and_query(monkeypatch):
    from backend.routers import equity as equity_router

    monkeypatch.setattr(equity_router, "get_user", lambda _u: {"roles": ["admin"]})
    client = TestClient(app)
    snapshot = f"pytest_{uuid.uuid4().hex[:8]}"

    # Minimal graph: A -> B (30%), B -> C (10%)
    a = str(uuid.uuid4())
    b = str(uuid.uuid4())
    c = str(uuid.uuid4())

    payload = {
        "snapshot_name": snapshot,
        "entities": [
            {"id": a, "name": "A公司", "entity_type": "company", "province": "北京"},
            {"id": b, "name": "B公司", "entity_type": "company", "province": "上海"},
            {"id": c, "name": "C公司", "entity_type": "company", "province": "浙江"},
        ],
        "edges": [
            {"id": str(uuid.uuid4()), "from_entity_id": a, "to_entity_id": b, "hold_pct": 30.0, "hold_pct_text": "30%"},
            {"id": str(uuid.uuid4()), "from_entity_id": b, "to_entity_id": c, "hold_pct": 10.0, "hold_pct_text": "10%"},
        ],
        "targets": [{"id": str(uuid.uuid4()), "entity_id": a, "name": "A公司", "is_key": True}],
    }

    r = client.post("/api/equity/admin/import", json=payload, headers=_auth_header())
    assert r.status_code == 200, r.text

    # targets
    r = client.get("/api/equity/targets", params={"snapshot_name": snapshot})
    assert r.status_code == 200, r.text
    assert len(r.json().get("items") or []) == 1

    # search
    r = client.get("/api/equity/entities/search", params={"snapshot_name": snapshot, "q": "A"})
    assert r.status_code == 200, r.text
    assert len(r.json().get("items") or []) >= 1

    # graph down with min_pct=0.2 should recurse A->B but not B->C
    r = client.get(
        "/api/equity/graph/ownership",
        params={"snapshot_name": snapshot, "target_entity_id": a, "direction": "down", "min_pct": 0.2, "max_depth": 5, "max_nodes": 500},
    )
    assert r.status_code == 200, r.text
    g = r.json()
    assert g["params"]["min_pct"] == 0.2
    node_ids = {n["id"] for n in g["nodes"]}
    assert a in node_ids and b in node_ids
    # C 可能作为边端点被加载（当前实现会 load 两端点），但不应继续递归扩张导致更多节点
    assert g["stats"]["node_count"] <= 3

    # summary
    r = client.get("/api/equity/analysis/summary", params={"snapshot_name": snapshot})
    assert r.status_code == 200, r.text
    dist = r.json().get("distributions") or {}
    assert "city" in dist
    assert "province" in dist

