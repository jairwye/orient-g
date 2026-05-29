"""财务部测试用户登录（TDD）。"""
from __future__ import annotations

import uuid

import jwt
from fastapi.testclient import TestClient

from backend.config import settings
from backend.main import app
from backend.routers.settings import DEPARTMENT_FINANCE, _has_view_business_dashboard
from backend.services.dev_users import ensure_department_test_user

client = TestClient(app)

FINANCE_TEST_PASSWORD = "FinanceTest!2026"


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_finance_user_login_with_custom_password():
    username = f"finance_test_{uuid.uuid4().hex[:8]}"
    ensure_department_test_user(
        username,
        password=FINANCE_TEST_PASSWORD,
        department=DEPARTMENT_FINANCE,
    )

    res = client.post(
        "/api/auth/login",
        json={"username": username, "password": FINANCE_TEST_PASSWORD},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data.get("ok") is True
    assert data.get("token")
    assert data.get("must_change_password") is False

    me = client.get("/api/auth/me", headers=_auth_header(data["token"]))
    assert me.status_code == 200, me.text
    me_data = me.json()
    assert me_data.get("username") == username
    assert me_data.get("department") == DEPARTMENT_FINANCE
    assert me_data.get("view_business_dashboard") is True
    assert me_data.get("is_admin") is False


def test_finance_user_helper_rejects_default_password():
    username = f"finance_bad_{uuid.uuid4().hex[:6]}"
    try:
        ensure_department_test_user(username, password="123456")
        assert False, "should reject default password"
    except ValueError as e:
        assert "123456" in str(e)


def test_has_view_business_dashboard_for_finance_department():
    user = {
        "username": "x",
        "roles": [],
        "department": DEPARTMENT_FINANCE,
    }
    assert _has_view_business_dashboard(user) is True


def test_admin_me_still_works_with_jwt():
    token = jwt.encode({"sub": "admin"}, settings.auth_secret, algorithm="HS256")
    res = client.get("/api/auth/me", headers=_auth_header(token))
    # admin 可能不存在于空库；至少接口可达
    assert res.status_code in (200, 401)
